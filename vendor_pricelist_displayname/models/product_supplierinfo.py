# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.osv.expression import get_unaccent_wrapper
from odoo.addons.base.models import res_partner
        
class ProductSupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    display_name = fields.Char(
            string='Name', compute='_compute_display_name',
    )

    @api.one
    @api.depends('product_code')
    def _compute_display_name(self):
        self.display_name = self.product_code
