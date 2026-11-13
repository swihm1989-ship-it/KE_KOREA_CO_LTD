"""160 synthetic transaction mails; no real customer data or credentials.

Facts are generated once as a golden provider-response fixture. These are
transport/mapping/evidence/calculation tests, not a claim of live LLM accuracy.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage

REQUESTS = [
    ('Please provide PI for below:', ('PI',)),
    ('Kindly send a proforma invoice for the following goods.', ('PI',)),
    ('Please provide a quotation for below:', ('PI',)),
    ('아래 조건으로 견적서를 작성해 주세요.', ('PI',)),
    ('Please prepare PO for below:', ('PO',)),
    ('구매 발주서를 작성해 주세요.', ('PO',)),
    ('Please prepare the commercial invoice.', ('CI',)),
    ('Please prepare a packing list.', ('PL',)),
    ('Please provide CIPL for this shipment.', ('CI','PL')),
    ('CI/PL을 만들어 주세요.', ('CI','PL')),
    ('Please draft a sales contract.', ('CONTRACT',)),
    ('아래 조건의 영문 계약서를 작성해 주세요.', ('CONTRACT',)),
    ('Please prepare PI and a sales contract.', ('PI','CONTRACT')),
    ('Please provide CIPL and a contract.', ('CI','PL','CONTRACT')),
    ('PI 및 Packing List를 작성해 주세요.', ('PI','PL')),
    ('Please prepare the purchase order and a contract.', ('PO','CONTRACT')),
]


def cases():
    result=[]
    for index in range(160):
        request,kinds=REQUESTS[index%len(REQUESTS)]
        purchase='PO' in kinds
        currency=('USD','EUR','KRW','CNY')[index%4]
        unit=('PCS','KG')[index%2]
        count=2 if index%3==0 else 1
        qty=0 if index%19==0 else (index+1)*1000
        price=Decimal('1250') if currency=='KRW' else Decimal('0.225')
        seller={'legal_name':'Synthetic Supplier Ltd' if purchase else 'KE KOREA CO. LTD',
                'address':'12 Test Avenue, Seoul', 'country':'South Korea'}
        buyer={'legal_name':'KE KOREA CO. LTD' if purchase else f'Synthetic Buyer {index:03} Ltd',
               'address':'34 Example Avenue, Wuxi', 'country':'China'}
        product='Synthetic Copper' if unit=='KG' else 'Synthetic M10 Solar Cell'
        items=[]
        lines=[]
        for row in range(count):
            quantity=qty+row
            name=product+f' Type {row+1}'
            line=f'Product: {name}; Quantity: {quantity:,} {unit}; Unit Price: {currency} {price}/{unit}; NW: {10+row} KG; GW: {12+row} KG; Volume: 0.1 CBM; Packages: 1 CTN'
            lines.append(line)
            items.append({'product_name':name,'quantity':str(quantity),'unit':unit,
                          'unit_price':str(price),'price_basis':unit,'source':line,
                          'net_weight_kg':str(10+row),'gross_weight_kg':str(12+row),
                          'volume_cbm':'0.1','package_count':'1','package_type':'CTN'})
        incoterm=('EXW Test Warehouse','FOB Test Port','CIF Example Port','DAP Example City')[index%4]
        payment='10% deposit and 90% before pickup'
        body=('Dear. Mr.David,\n'+request+'\n'
              f'Seller: {seller["legal_name"]}; Seller Address: {seller["address"]}\n'
              f'Buyer: {buyer["legal_name"]}; Buyer Address: {buyer["address"]}\n'+ '\n'.join(lines)+
              f'\nCurrency: {currency}\nIncoterms: {incoterm}\nPayment: {payment}\n'
              f'Shipment Reference: SYN-{index:03}\nCountry of Origin: South Korea\n'
              f'Actual Package Count: {count}\nNet Weight: {sum(10+r for r in range(count))} KG\n'
              f'Gross Weight: {sum(12+r for r in range(count))} KG\nVolume: {Decimal("0.1")*count} CBM\n')
        trade={'document_type':next(k for k in kinds if k!='CONTRACT') if kinds!=('CONTRACT',) else 'PI',
               'product_family':'solar_cell','seller':seller,'buyer':buyer,'currency':currency,
               'items':items,'incoterms':incoterm,'payment_terms':payment,'document_number':'DRAFT',
               'shipment_reference':f'SYN-{index:03}','country_of_origin':'South Korea',
               'actual_package_count':str(count),'declared_net_weight_kg':str(sum(10+r for r in range(count))),
               'declared_gross_weight_kg':str(sum(12+r for r in range(count))),
               'declared_volume_cbm':str(Decimal('0.1')*count),
               'missing_fields':[],'conflicts':[],'source_notes':lines}
        # Match the actual strict API schema: nullable required fields are present.
        from Quotation_KEKOREA.agent.extractor import _schema
        schema=_schema()
        for item in trade['items']:
            for key in schema['properties']['items']['items']['required']:
                item.setdefault(key,None)
        for role in ('seller','buyer'):
            trade[role]={k:v for k,v in trade[role].items() if k in schema['properties'][role]['properties']}
            for key in schema['properties'][role]['required']:
                trade[role].setdefault(key,None)
        for key in schema['required']:
            trade.setdefault(key,None)
        terms={'products':items[0]['product_name'],'quantity':items[0]['quantity'],'unit':unit,
               'unit_price':str(price),'currency':currency,'delivery':incoterm,'payment_trigger':payment}
        analysis={'contract_type':'sale','parties':[dict(seller,roles=['seller']),dict(buyer,roles=['buyer'])],
                  'terms':[{'key':k,'value':v,'status':'suggested','source_refs':[]} for k,v in terms.items()],
                  'questions':[],'issues':[]}
        mail=EmailMessage();mail['From']=f'Synthetic Buyer <buyer{index}@example.test>'
        mail['Subject']=f'Transaction request {index:03}'
        mail.set_content(body)
        result.append({'id':f'mail-{index:03}','raw':mail.as_bytes(),'subject':str(mail['Subject']),
                       'body':body,'kinds':kinds,'trade':trade,'analysis':analysis,
                       'expected_total':sum((Decimal(i['quantity'])*price).quantize(Decimal('1') if currency=='KRW' else Decimal('0.01'),rounding=ROUND_HALF_UP) for i in items)})
    return result
