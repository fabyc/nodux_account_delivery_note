#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import Workflow
from trytond.model import ModelView, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import If, Eval, Bool, Id
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.transaction import Transaction
from trytond.modules.company import CompanyReport
from trytond.wizard import Wizard, StateView, StateTransition, StateAction, \
    Button
from decimal import Decimal

conversor = None
try:
    from numword import numword_es
    conversor = numword_es.NumWordES()
except:
    print("Warning: Does not possible import numword module!")
    print("Please install it...!")

__all__ = ['Invoice', 'OutInvoiceStart', 'OutInvoice']
        
__metaclass__ = PoolMeta

_STATES = {
    'readonly': Eval('state') != 'draft',
}
_DEPENDS = ['state']

_TYPE = [
    ('delivery_note','Nota de Entrega'),
]

_TYPE2JOURNAL = {
    'out_withholding': 'revenue',
    'in_withholding': 'expense',
    'anticipo':'revenue',    
    'out_invoice': 'revenue',
    'in_invoice': 'expense',
    'out_credit_note': 'revenue',
    'in_credit_note': 'expense',
    'delivery_note': 'revenue',
}

_ZERO = Decimal('0.0')

_DELIVERY_TYPE = {
    'delivery_note': 'out_invoice',
    }
    
class Invoice:
    'Invoice'
    __name__ = 'account.invoice'  

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls.state_string = super(Invoice, cls).state.translated('state')
        new_sel = [
            ('delivery_note', 'Nota de Entrega')
        ]
        if new_sel not in cls.type.selection:
            cls.type.selection.extend(new_sel)
    
            
    @fields.depends('type', 'party', 'company')
    def on_change_type(self):
        Journal = Pool().get('account.journal')
        res = {}
        journals = Journal.search([
                ('type', '=', _TYPE2JOURNAL.get(self.type or 'delivery_note',
                        'revenue')),
                ], limit=1)
        if journals:
            journal, = journals
            res['journal'] = journal.id
            res['journal.rec_name'] = journal.rec_name
        res.update(self.__get_account_payment_term())
        return res  
        
    def set_number(self):
        '''
        Set number to the invoice
        '''
        pool = Pool()
        Period = pool.get('account.period')
        Sequence = pool.get('ir.sequence.strict')
        Date = pool.get('ir.date')            
        if self.number: 
            return

        test_state = True
        if self.type in ('in_invoice', 'in_credit_note'):
            test_state = False

        accounting_date = self.accounting_date or self.invoice_date
        period_id = Period.find(self.company.id,
            date=accounting_date, test_state=test_state)
        period = Period(period_id)
        sequence = period.get_invoice_sequence(self.type)
        if not sequence:
            self.raise_user_error('no_invoice_sequence', {
                    'invoice': self.rec_name,
                    'period': period.rec_name,
                    })
        with Transaction().set_context(
                date=self.invoice_date or Date.today()):
            number = Sequence.get_id(sequence.id)
            vals = {'number': number}
            if (not self.invoice_date
                    and self.type in ('out_invoice', 'out_credit_note')):
                vals['invoice_date'] = Transaction().context['date']
        self.write([self], vals)               

    
                
    def _out_invoice(self):
        res = {}
        res['type'] = _DELIVERY_TYPE[self.type]
        for field in ('description', 'comment'):
            res[field] = getattr(self, field)

        for field in ('company', 'party', 'invoice_address', 'currency',
                'journal', 'account', 'payment_term'):
            res[field] = getattr(self, field).id
        
        res['lines'] = []
        if self.lines:
            res['lines'].append(('create',
                    [line._credit() for line in self.lines]))

        res['taxes'] = []
        to_create = [tax._credit() for tax in self.taxes if tax.manual]
        if to_create:
            res['taxes'].append(('create', to_create))
        return res
        
    
    @classmethod
    def out_invoice(cls, invoices, refund=False):

        MoveLine = Pool().get('account.move.line')

        new_invoices = []
        for invoice in invoices:
            new_invoice, = cls.create([invoice._out_invoice()])
            new_invoices.append(new_invoice)
            if refund:
                cls.post([new_invoice])
                if new_invoice.state == 'posted':
                    MoveLine.reconcile([l for l in invoice.lines_to_pay
                            if not l.reconciliation] +
                        [l for l in new_invoice.lines_to_pay
                            if not l.reconciliation])
        cls.update_taxes(new_invoices)
        return new_invoices
        
    @classmethod
    @ModelView.button
    @Workflow.transition('validated')
    def validate_invoice(cls, invoices):
        for invoice in invoices:
            print "Esta ingresando aqui*** validar** delivery"
            if invoice.type in ('in_withholding', 'out_withholding'):
                #invoice.get_ventas()
                invoice.set_number()
                invoice.create_move()
            if invoice.type in ('delivery_note'):
                #invoice.get_ventas()
                invoice.set_number()
                
    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, invoices):
        Move = Pool().get('account.move')
        moves = []
        for invoice in invoices:
            print "Esta ingresando aqui*** contabilizar DELIVERY**"
            invoice.set_number()
            moves.append(invoice.create_move())
        for invoice in invoices:
            if invoice.type in ('out_withholding'):
                invoice.get_value()
        cls.write([i for i in invoices if i.state != 'posted'], {
                'state': 'posted',
                })
        Move.post([m for m in moves if m.state != 'posted'])              
        
        for invoice in invoices:
            if invoice.type in ('out_invoice', 'out_credit_note'):
                invoice.print_invoice()
                
class OutInvoiceStart(ModelView):
    'Invoice Start'
    __name__ = 'nodux_account_delivery_note.out_invoice.start'
    
class OutInvoice(Wizard):
    'Out Invoice'
    __name__ = 'nodux_account_delivery_note.out_invoice'
    #crear referencias:
    start = StateView('nodux_account_delivery_note.out_invoice.start',
        'nodux_account_delivery_note.out_invoice_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Invoice', 'invoice', 'tryton-ok', default=True),
            ])
    invoice = StateAction('account_invoice.act_invoice_form')
        
    @classmethod
    def __setup__(cls):
        super(OutInvoice, cls).__setup__()
     
    def do_invoice(self, action):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        invoices = Invoice.browse(Transaction().context['active_ids'])

        out_invoices = Invoice.out_invoice(invoices)

        data = {'res_id': [i.id for i in out_invoices]}
        if len(out_invoices) == 1:
            action['views'].reverse()
            
        return action, data
        
