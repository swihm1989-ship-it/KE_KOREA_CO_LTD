"""Mirror legacy nullable-quantity and explicit-destination rules for mail input.

No template changes and no inferred price, quantity, delivery address or approval.
"""
from decimal import Decimal, InvalidOperation
import re


def explicit_ship_to(text):
    return bool(re.search(r'\b(?:ship[\s-]*to(?:\s+address)?|deliver(?:ed)?\s+to|delivery\s+(?:to|address|location)|destination|consignee\s+address)\b\s*[:=]|배송지\s*[:=]|수령\s*주소\s*[:=]',str(text or ''),re.I))


def synchronize_nullable_quantities(data):
    for item in data.get('items') or []:
        paid=item.get('paid_quantity') if item.get('promotion') else item.get('quantity')
        if paid in (None,''):
            paid=next((item.get(k) for k in ('quantity','paid_quantity') if item.get(k) not in (None,'')),None)
        if paid not in (None,''):
            # Retain conflicting explicit paid/shipped facts for the validator.
            if item.get('paid_quantity') in (None,''):
                item['paid_quantity']=str(paid)
            if item.get('quantity') in (None,''):
                item['quantity']=str(paid)
            if item.get('free_quantity') in (None,''):
                if item.get('promotion'):
                    from Quotation_KEKOREA.agent.trade_documents import apply_promotion
                    try:
                        item['free_quantity']=apply_promotion(paid,item['promotion'])['free_quantity']
                    except (ValueError,InvalidOperation):
                        pass
                else:
                    item['free_quantity']='0'
            if item.get('shipped_quantity') in (None,''):
                try:
                    item['shipped_quantity']=format(Decimal(str(paid))+Decimal(str(item['free_quantity'])),'f')
                except (InvalidOperation,ValueError,TypeError,KeyError):
                    pass
        # None from strict JSON is absence; the existing non-cosmetics default is 0.
        # Cosmetics still requires the existing explicit discount confirmation.
        if data.get('product_family')!='cosmetics' and item.get('discount_percent') is None:
            item.pop('discount_percent',None)
    return data


def resolve_notice_for_answer(document,key):
    """Clear only exact missing labels for a fact a human actually edited."""
    aliases={key.casefold(),key.replace('.',' ').replace('_',' ').casefold()}
    if key.startswith(('buyer.','seller.')):
        role,field=key.split('.',1)
        aliases.add(f'{role} {field.replace("_"," ")}')
        label='Buyer / customer' if role=='buyer' else 'Seller / supplier'
        aliases.add((label+': '+field.replace('_',' ')).casefold())
    elif key.startswith('item.'):
        field=key.split('.',1)[1]
        aliases.update({field.replace('_',' '),f'item 1: {field.replace("_"," ")}'})
    else:
        aliases.add(key.replace('_',' '))
    document['missing_fields']=[notice for notice in document.get('missing_fields') or []
                                if str(notice).strip().casefold() not in aliases]
    return document


def apply_quantity_edit(item,value):
    """An explicit paid-quantity edit must change the quantity used for amounts."""
    item['quantity']=value
    item['paid_quantity']=value
    try:
        paid=Decimal(str(value).replace(',',''))
        if item.get('promotion'):
            from Quotation_KEKOREA.agent.trade_documents import apply_promotion
            item['free_quantity']=apply_promotion(paid,item['promotion'])['free_quantity']
        free=Decimal(str(item.get('free_quantity') or '0'))
        item['shipped_quantity']=format(paid+free,'f')
    except (ValueError,TypeError,InvalidOperation):
        pass # Deterministic legacy validation keeps invalid inputs blocked.
    return item
