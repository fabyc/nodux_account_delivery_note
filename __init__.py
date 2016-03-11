#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.pool import Pool
from .invoice import *
from .account import *
def register():
    Pool.register(
        FiscalYear, 
        Period,
        Invoice,
        OutInvoiceStart, 
        module='nodux_account_delivery_note', type_='model')
    Pool.register(
        OutInvoice, 
        module='nodux_account_delivery_note', type_='wizard')
