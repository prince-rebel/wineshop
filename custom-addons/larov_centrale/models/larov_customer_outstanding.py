# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools

PARAM_RISK_HIGH = 'larov_centrale.risk_high_amount'
PARAM_RISK_MEDIUM = 'larov_centrale.risk_medium_amount'


class LarovCustomerOutstanding(models.Model):
    """Encours clients : une ligne par facture client comptabilisée, avec
    reste à payer, échéance, retard, statut, niveau de risque et relance.

    Vue SQL en lecture seule sur les factures (Facturation). Reprend les
    colonnes du tableau « ENCOURS CLIENTS » du client. Les factures sont
    lues au niveau du client commercial (société), pas du contact.
    """
    _name = 'larov.customer.outstanding'
    _description = 'Encours clients'
    _auto = False
    _rec_name = 'move_name'
    _order = 'amount_residual desc, invoice_date'

    move_id = fields.Many2one('account.move', string='Facture', readonly=True)
    move_name = fields.Char(string='N° facture', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    customer_segment = fields.Selection([
        ('chr', 'CHR externe'), ('group', 'Groupe'),
        ('individual', 'Particulier'), ('company', 'Entreprise (cadeaux)'),
    ], string='Type', readonly=True)
    commercial_zone_id = fields.Many2one('larov.commercial.zone', string='Secteur', readonly=True)
    payment_term_id = fields.Many2one('account.payment.term', string='Conditions', readonly=True)
    invoice_date = fields.Date(string='Date facture', readonly=True)
    invoice_date_due = fields.Date(string='Échéance', readonly=True)
    invoice_origin = fields.Char(string='Référence (BL / commande)', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    amount_total = fields.Monetary(string='Montant facturé', readonly=True)
    amount_paid = fields.Monetary(string='Déjà réglé', readonly=True)
    amount_residual = fields.Monetary(string='Reste à payer', readonly=True)
    days_overdue = fields.Integer(string='Jours de retard', readonly=True)
    status = fields.Selection([
        ('paid', 'Soldée'), ('overdue', 'Échue'), ('upcoming', 'À venir'),
    ], string='Statut', readonly=True)
    aging_bucket = fields.Selection([
        ('not_due', 'Non échu'), ('b1_30', '1 à 30 jours'), ('b31_60', '31 à 60 jours'),
        ('b61_90', '61 à 90 jours'), ('b90', 'Plus de 90 jours'), ('paid', 'Soldée'),
    ], string='Ancienneté', readonly=True)
    risk_level = fields.Selection([
        ('high', 'Élevé'), ('medium', 'Moyen'), ('low', 'Faible'), ('none', '—'),
    ], string='Niveau', compute='_compute_risk')
    to_remind = fields.Boolean(string='À relancer ?', compute='_compute_risk')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    am.id                                   AS id,
                    am.id                                   AS move_id,
                    am.name                                 AS move_name,
                    am.commercial_partner_id                AS partner_id,
                    rp.customer_segment                     AS customer_segment,
                    rp.commercial_zone_id                   AS commercial_zone_id,
                    am.invoice_payment_term_id              AS payment_term_id,
                    am.invoice_date                         AS invoice_date,
                    COALESCE(am.invoice_date_due, am.invoice_date) AS invoice_date_due,
                    am.invoice_origin                       AS invoice_origin,
                    am.company_id                           AS company_id,
                    am.currency_id                          AS currency_id,
                    am.amount_total_signed                  AS amount_total,
                    am.amount_total_signed - am.amount_residual_signed AS amount_paid,
                    am.amount_residual_signed               AS amount_residual,
                    CASE WHEN am.amount_residual_signed <= 0 THEN 0
                         ELSE GREATEST(0, (CURRENT_DATE - COALESCE(am.invoice_date_due, am.invoice_date)))
                    END                                     AS days_overdue,
                    CASE WHEN am.amount_residual_signed <= 0 THEN 'paid'
                         WHEN CURRENT_DATE > COALESCE(am.invoice_date_due, am.invoice_date) THEN 'overdue'
                         ELSE 'upcoming'
                    END                                     AS status,
                    CASE WHEN am.amount_residual_signed <= 0 THEN 'paid'
                         WHEN CURRENT_DATE <= COALESCE(am.invoice_date_due, am.invoice_date) THEN 'not_due'
                         WHEN CURRENT_DATE - COALESCE(am.invoice_date_due, am.invoice_date) <= 30 THEN 'b1_30'
                         WHEN CURRENT_DATE - COALESCE(am.invoice_date_due, am.invoice_date) <= 60 THEN 'b31_60'
                         WHEN CURRENT_DATE - COALESCE(am.invoice_date_due, am.invoice_date) <= 90 THEN 'b61_90'
                         ELSE 'b90'
                    END                                     AS aging_bucket
                FROM account_move am
                JOIN res_partner rp ON rp.id = am.commercial_partner_id
                WHERE am.move_type IN ('out_invoice', 'out_refund')
                  AND am.state = 'posted'
            )
        """ % self._table)

    @api.depends('amount_residual', 'customer_segment', 'status')
    def _compute_risk(self):
        icp = self.env['ir.config_parameter'].sudo()
        high = float(icp.get_param(PARAM_RISK_HIGH, 2000000))
        medium = float(icp.get_param(PARAM_RISK_MEDIUM, 500000))
        for rec in self:
            residual = rec.amount_residual
            if residual >= high:
                rec.risk_level = 'high'
            elif residual >= medium:
                rec.risk_level = 'medium'
            elif residual > 0:
                rec.risk_level = 'low'
            else:
                rec.risk_level = 'none'
            rec.to_remind = bool(residual >= medium and rec.status == 'overdue' and rec.customer_segment == 'chr')

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class ResPartnerStatement(models.Model):
    _inherit = 'res.partner'

    def _larov_statement_lines(self, months_back=6):
        """Factures à faire figurer sur le relevé d'échéances : toutes les
        factures non soldées + celles soldées sur les N derniers mois."""
        self.ensure_one()
        from dateutil.relativedelta import relativedelta
        date_from = fields.Date.context_today(self) - relativedelta(months=months_back)
        Outstanding = self.env['larov.customer.outstanding']
        lines = Outstanding.search([
            ('partner_id', '=', self.commercial_partner_id.id),
            '|', ('status', '!=', 'paid'), ('invoice_date', '>=', date_from),
        ], order='invoice_date, move_name')
        return lines

    def _larov_statement_totals(self, lines):
        buckets = {'not_due': 0.0, 'b1_30': 0.0, 'b31_60': 0.0, 'b61_90': 0.0, 'b90': 0.0}
        for l in lines:
            if l.aging_bucket in buckets:
                buckets[l.aging_bucket] += l.amount_residual
        total_due = sum(lines.mapped('amount_residual'))
        return {
            'total_due': total_due,
            'overdue': sum(l.amount_residual for l in lines if l.status == 'overdue'),
            'upcoming': sum(l.amount_residual for l in lines if l.status == 'upcoming'),
            'buckets': buckets,
            'bucket_pct': {k: (v / total_due * 100.0) if total_due else 0.0 for k, v in buckets.items()},
        }
