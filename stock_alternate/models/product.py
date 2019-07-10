# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError

class ProductAlternative(models.Model):
    _name = 'product.alternative'
    _description = 'Alternate Product'

    product_tmpl_id = fields.Many2one('product.template', string='Original')
    product_alt_id = fields.Many2one('product.template', string='Product')
    default_code = fields.Char(related='product_alt_id.default_code', string="SKU")
    list_price = fields.Float(related='product_alt_id.list_price', string="Sales Price")
    standard_price = fields.Float(related='product_alt_id.standard_price', string="Cost")
    manufacturer = fields.Many2one(related='product_alt_id.manufacturer', string="Manufacturer")
    manufacturer_pref = fields.Char(related='product_alt_id.manufacturer_pref',string='Manuf. SKU')
    qty_available = fields.Float(related='product_alt_id.qty_available', string="On Hand")
    virtual_available = fields.Float(related='product_alt_id.virtual_available', string="Forecasted")

    @api.multi
    def unlink(self):
        for record in self:
          result = self.env.cr.execute('delete from product_alternative where product_tmpl_id = %s or product_alt_id = %s' % (record.product_alt_id.id,record.product_alt_id.id) )
        return super(ProductAlternative, self).unlink()

    @api.model
    def create(self, vals):
        res = super(ProductAlternative, self).create(vals)

        # prevent recursive calls
        if 'stop' in vals:
          return res

        # check for recursive data entry
        if vals['product_tmpl_id'] == vals['product_alt_id']:
            raise UserError("Product cannot be an alternative of itself!")

        # get a list of alternates for the alternate product
        existing_alternates = self.env['product.alternative'].search([('product_tmpl_id','=',vals['product_tmpl_id']),
                                                              ('product_alt_id','!=',vals['product_alt_id'])])

        for alt in existing_alternates:
          #_logger.warning("EXISTING ALTERNATIVE FOUND")
          #_logger.warning("tmpl= "+str(alt.product_tmpl_id.id)+", alt="+ str(alt.product_alt_id.id))
          alt_exists = self.env['product.alternative'].search([('product_tmpl_id','=',alt.product_alt_id.id),
                                                              ('product_alt_id','=',vals['product_alt_id'])])

          if not alt_exists:
            #_logger.warning("ALT DOESNT EXIST")
            #_logger.warning("tmpl= "+str(alt.product_tmpl_id.id)+", alt="+ str(vals['product_alt_id']))
            new_alt={}
            new_alt['product_tmpl_id'] = alt.product_alt_id.id
            new_alt['product_alt_id'] = vals['product_alt_id']
            new_alt['stop'] = True
            res2 = self.create(new_alt)

          alt_inverse_exists = self.env['product.alternative'].search([('product_tmpl_id','=',vals['product_alt_id']),
                                                              ('product_alt_id','=',alt.product_alt_id.id)])
          if not alt_inverse_exists:
            #_logger.warning("ALT INVERSE DOESNT EXIST")
            #_logger.warning("tmpl= "+str(vals['product_alt_id'])+", alt="+ str(alt.product_alt_id.id))
            new_alt_inv={}
            new_alt_inv['product_tmpl_id'] = vals['product_alt_id']
            new_alt_inv['product_alt_id'] = alt.product_alt_id.id
            new_alt_inv['stop'] = True
            res3 = self.create(new_alt_inv)


        # check if the reverse relationship exists
        inverse_exists = self.env['product.alternative'].search([('product_tmpl_id','=',vals['product_alt_id']),
                                                        ('product_alt_id','=',vals['product_tmpl_id'])])

        if not inverse_exists:
          #_logger.warning("CREATING ALTERNATE")
          inverse_product = self.env['product.template'].search([('id','=',vals['product_alt_id'])])
          new_inverse = {}
          new_inverse['product_tmpl_id'] = vals['product_alt_id']
          new_inverse['product_alt_id'] = vals['product_tmpl_id']
          new_inverse['stop'] = True
          res4 = self.create(new_inverse)

        return res

class ProductTemplate(models.Model):
    _inherit = "product.template"

    alternate_ids = fields.One2many('product.alternative','product_tmpl_id','Alternates')

    ph_qty_available = fields.Float(
        "Quantity On Hand (incl. alt)",
        store=False,
        readonly=True,
        compute="_compute_ph_quantities",
        search="_search_ph_qty_available",
        digits=dp.get_precision("Product Unit of Measure"),
    )

    ph_virtual_available = fields.Float(
        "Forecasted Quantity (incl. alt)",
        store=False,
        readonly=True,
        compute="_compute_ph_quantities",
        search="_search_ph_virtual_available",
        digits=dp.get_precision("Product Unit of Measure"),
    )

    ph_incoming_qty = fields.Float(
        "Incoming (incl. alt)",
        store=False,
        readonly=True,
        compute="_compute_ph_quantities",
        search="_search_ph_incoming_qty",
        digits=dp.get_precision("Product Unit of Measure"),
    )

    ph_outgoing_qty = fields.Float(
        "Outgoing (incl. alt)",
        store=False,
        readonly=True,
        compute="_compute_ph_quantities",
        search="_search_ph_outgoing_qty",
        digits=dp.get_precision("Product Unit of Measure"),
    )

    def action_open_ph_quants(self):
        self.env["stock.quant"]._merge_quants()
        self.env["stock.quant"]._unlink_zero_quants()
        products = self.mapped("product_variant_ids")
        products |= (
            self.mapped("alternate_ids")
            .mapped("product_alt_id")
            .mapped("product_variant_ids")
        )
        products = self.mapped("alternate_ids").mapped("product_alt_id").mapped("product_variant_ids")
        action = self.env.ref("stock.product_open_quants").read()[0]
        action["domain"] = [("product_id", "in", products.ids)]
        action["context"] = {"search_default_internal_loc": 1}
        return action

    @api.multi
    def _compute_ph_quantities(self):
        res = self._compute_ph_quantities_dict()
        for template in self:
            template.ph_qty_available = res[template.id]["qty_available"]
            template.ph_virtual_available = res[template.id]["virtual_available"]
            template.ph_incoming_qty = res[template.id]["incoming_qty"]
            template.ph_outgoing_qty = res[template.id]["outgoing_qty"]

    def _compute_ph_quantities_dict(self):
        self_variants = self.mapped("product_variant_ids")
        self_variants |= (
            self.mapped("alternate_ids").mapped("product_alt_id").mapped("product_variant_ids")
        )
        self_variants = self.mapped("alternate_ids").mapped("product_alt_id").mapped("product_variant_ids")
        variants_available = self_variants._product_available()
        prod_available = {}
        for template in self:
            qty_available = 0
            virtual_available = 0
            incoming_qty = 0
            outgoing_qty = 0
            for p in variants_available.items():
                qty_available += p[1]["qty_available"]
                virtual_available += p[1]["virtual_available"]
                incoming_qty += p[1]["incoming_qty"]
                outgoing_qty += p[1]["outgoing_qty"]
            prod_available[template.id] = {
                "qty_available": qty_available,
                "virtual_available": virtual_available,
                "incoming_qty": incoming_qty,
                "outgoing_qty": outgoing_qty,
            }
        return prod_available

    @api.multi
    def action_open_ph_quants_unreserved(self):
        product_ids = self.mapped("product_variant_ids")
        product_ids |= (
            self.mapped("alternate_ids")
            .mapped("product_alt_id")
            .mapped("product_variant_ids")
        )
        product_ids = product_ids.ids
        quants = self.env["stock.quant"].search([("product_id", "in", product_ids)])
        quant_ids = quants.filtered(lambda x: x.quantity > x.reserved_quantity).ids
        result = self.env.ref("stock.product_open_quants").read()[0]
        result["domain"] = [("id", "in", quant_ids)]
        result["context"] = {
            "search_default_locationgroup": 1,
            "search_default_internal_loc": 1,
        }
        return result

    @api.multi
    def action_open_ph_forecast(self):
        product_ids = self.mapped("product_variant_ids")
        product_ids |= (
            self.mapped("alternate_ids")
            .mapped("product_alt_id")
            .mapped("product_variant_ids")
        )
        product_ids = self.mapped("alternate_ids").mapped("product_alt_id").mapped("product_variant_ids")
        product_ids = product_ids.ids
        result = self.env.ref(
            "stock.action_stock_level_forecast_report_template"
        ).read()[0]
        result["domain"] = [("product_id", "in", product_ids)]
        result["context"] = {"group_by": ["product_id"]}
        return result

    def _search_ph_qty_available(self, operator, value):
        domain = [("ph_qty_available", operator, value)]
        product_variant_ids = self.env["product.product"].search(domain)
        return [("product_variant_ids", "in", product_variant_ids.ids)]

    def _search_ph_virtual_available(self, operator, value):
        domain = [("ph_virtual_available", operator, value)]
        product_variant_ids = self.env["product.product"].search(domain)
        return [("product_variant_ids", "in", product_variant_ids.ids)]

    def _search_ph_incoming_qty(self, operator, value):
        domain = [("ph_incoming_qty", operator, value)]
        product_variant_ids = self.env["product.product"].search(domain)
        return [("product_variant_ids", "in", product_variant_ids.ids)]

    def _search_ph_outgoing_qty(self, operator, value):
        domain = [("ph_outgoing_qty", operator, value)]
        product_variant_ids = self.env["product.product"].search(domain)
        return [("product_variant_ids", "in", product_variant_ids.ids)]


