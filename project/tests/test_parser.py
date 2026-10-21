import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.parser import (
    _extract_items_from_text, _extract_export_date, _extract_carton_range,
    _clean_material_description, _aggregate_items, _material_heading, _extract_gross_weight, _extract_net_weight, parse_result,
)
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell
from src.foc_extractor.models import LineItem


class ParserTests(unittest.TestCase):
    def test_joined_qty_weight_header_uses_neighboring_quantity_column(self):
        rows=[['PARTICULARS','WOVEN / KNIT','','QTY (in Yard) WEIGHT / Kgs'],
              ['STYLE A\n53% COTTON 42% NYLON 5% METALLIC 3x3%\nSTYLE B\n100% POLYESTER LINING 3x3%\nSTYLE C\n63% LYOCELL 37% COTTON DENIM 4x4%',
               'WOVEN','25 YDS\n25 YDS\n20 YDS','5.27 KGS\n3.02 KGS\n6.10 KGS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('53% COTTON 42% NYLON 5% METALLIC WOVEN FABRICS',25,'YDS'),
                          ('100% POLYESTER WOVEN FABRICS',25,'YDS'),('63% LYOCELL 37% COTTON WOVEN FABRICS',20,'YDS')])

    def test_weight_column_cannot_supply_quantity_when_joined_header_is_unresolved(self):
        from src.foc_extractor.parser import _table_fields
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,2,'QTY WEIGHT / Kgs'),
               OCRTableCell(1,0,'COTTON'),OCRTableCell(1,1,'UNREADABLE'),OCRTableCell(1,2,'5 KGS')]
        self.assertEqual(_table_fields(OCRTable(cells,2,3)),({},-1))

    def test_unbounded_ocr_page_is_not_used_as_a_goods_table(self):
        from src.foc_extractor.ocr_engine import OCRWord
        data=parse_result(OCRResult(content='PACKING LIST\nSTAFF COPY 40 YDS',pages=['PACKING LIST\nSTAFF COPY 40 YDS'],
                                   words=[OCRWord('STAFF COPY 40 YDS',.99,10,30,150,50)]),Path('anonymous.pdf'))
        self.assertEqual(data.items,[])
        self.assertTrue(any('boundaries unavailable' in w for w in data.warnings))

    def test_printed_garment_title_in_phantom_neighbor_column_is_not_lost(self):
        rows=[['SENDER','EXTRA','PARTICULARS','QTY'],['A','STYLE: CODE-456 SLVS BELTED MAXI DRESS','','1 PCS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],[('SLVS BELTED MAXI DRESS',1,'PCS')])
        rows[1][1]='OTHER METADATA'
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('anonymous.pdf'))
        self.assertEqual(data.items,[])

    def test_per_item_weight_in_item_name_is_not_a_second_goods_quantity(self):
        rows=[['PARTICULARS','ITEM','QTY'],['PHOTO OF BUTTONS','SHANK & RIVET - 2G\nEACH ITEM & COLOR','600 PCS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),3)]),Path('anonymous.pdf'))
        self.assertEqual([(i.quantity,i.unit) for i in data.items],[(600,'PCS')])

    def test_named_split_products_keep_their_own_quantities(self):
        rows=[['PARTICULARS','QTY'],['STYLE BLOUSE\nFabric Hanger\n53% VISCOSE 47% COTTON\nSTYLE BLOUSE\nMF part card\nSTYLE BLOUSE\nEmby MF part card','2 PCS\n1 PCS\n2 PCS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('FABRIC HANGER',2,'PCS'),('MF PART CARD',1,'PCS'),('EMBY MF PART CARD',2,'PCS')])

    def test_felt_patch_label_survives_color_continuation(self):
        rows=[['PARTICULARS','QTY'],['Felt patch, Code: ABC, Size: 12mm',''],['COLOR WHITE','440 PCS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('FELT PATCH',440)])

    def test_wrapped_sender_keeps_material_and_late_fabric_kind(self):
        rows=[['SENDER','PARTICULARS','QTY','WOVEN / KNIT'],
              ['','100% COTTON','',''],['DEPT 8-','COLOR RED','20 YDS',''],
              ['ANOTHER NAME','COLOR BLUE','30 YDS','WOVEN'],
              ['DEPT 9','UNRELATED LABEL','2 PCS','']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('100% COTTON WOVEN FABRICS',50,'YDS'),('UNRELATED LABEL',2,'PCS')])

    def test_split_percentage_blend_completes_before_quantity_grouping(self):
        rows=[['SENDER','PARTICULARS','QTY','WOVEN / KNIT'],
              ['A','62% COTTON 21% POLYESTER 11% VISCOSE','70.5 YDS','WOVEN'],
              ['','6% SPANDEX DENIM','',''],['','COL BLACK','32 YDS','']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],
                         [('62% COTTON 21% POLYESTER 11% VISCOSE 6% SPANDEX WOVEN FABRICS',102.5)])
        rows[2][0]='B'
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('anonymous.pdf'))
        self.assertFalse(any(i.description.startswith('62% COTTON') and i.quantity==102.5 for i in data.items))

    def test_item_column_quantity_is_paired_without_copying_style_numbers(self):
        rows=[['PARTICULARS','ITEM','QTY'],
              ['STYLE 987 JACKET SHANK BUTTON X 2 GROSS DIE MOULD X 1 SET','SHANK BUTTON 2 GROSS +\nDIE MOULD','1 SET']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),3)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('SHANK BUTTON',2,'GROSS'),('DIE MOULD',1,'SETS')])

    def test_repeated_lace_product_uses_quantity_column_not_style_annotations(self):
        rows=[['PARTICULARS','QTY'],['STYLE A EC SAMPLE LACE 20Y\nSTYLE B EC SAMPLE LACE 6Y','30 YDS\n6 YDS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],[('EC SAMPLE LACE',36,'YDS')])

    def test_goods_names_remove_metadata_without_changing_product_identity(self):
        cases=[('BUYER SS28 Trouser STYLE 123 Brown Swatch - Color Standard','FABRIC SWATCHES'),
               ('BLUE FABRIC SWATCHES CARD STYLE ABC','FABRIC SWATCHES CARD'),
               ("BUYER FRILLED BLOUSE STYLE ABC MF SAMPLE WOMENS WOVEN MILL 53% VISCOSE 47% COTTON #60 - 1 PC",'53% VISCOSE 47% COTTON WOMENS WOVEN BLOUSE'),
               ('100% COTTON WOVEN FABRICS','100% COTTON WOVEN FABRICS'),
               ('9.5MM RIVET','9.5MM RIVET'),
               ('PAINT SWATCH - COLOR STANDARD','PAINT SWATCH - COLOR STANDARD'),
               ('BLOUSE WOMENS WOVEN 53% VISCOSE 40% COTTON','BLOUSE WOMENS WOVEN 53% VISCOSE 40% COTTON')]
        for source,expected in cases:
            with self.subTest(source=source):
                self.assertEqual(_clean_material_description(source),expected)
                self.assertEqual(_clean_material_description(expected),expected)
        self.assertEqual(_material_heading('STYLE ABC 60% BCL COTTON 40% RECYCLED POLYESTER','WOVEN'),
                         '60% COTTON 40% RECYCLED POLYESTER WOVEN FABRICS')
        self.assertIsNone(_material_heading('60% UNKNOWN 40% COTTON','WOVEN'))
        self.assertEqual(_material_heading('94% COTTON 6% STRETCH DYED FABRIC','WOVEN'),
                         '94% COTTON 6% STRETCH WOVEN FABRICS')

    def test_swatch_cleanup_merges_only_same_units_and_retains_source_rows(self):
        rows=[['PARTICULARS','QTY'],['TROUSER STYLE ABC Brown Swatch - Color Standard','1 PCS'],
              ['SHORT STYLE XYZ Black Swatch - Color Standard','2 PCS'],
              ['FABRIC SWATCHES','3 SETS']]
        cells=[OCRTableCell(r,c,value) for r,row in enumerate(rows) for c,value in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('FABRIC SWATCHES',3,'PCS'),('FABRIC SWATCHES',3,'SETS')])
        self.assertEqual(len(data.items[0].source_refs),2)

    def test_multiline_garments_keep_declared_gender_and_composition(self):
        rows=[['PARTICULARS','QTY'],["STYLE ABC MENS\n100% LINEN WOVEN SHIRT\n#50\nSTYLE DEF\n63% VISCOSE RAYON 37% POLYAMIDE WOVEN SHIRT",'2 PCS\n1 PCS']]
        cells=[OCRTableCell(r,c,value) for r,row in enumerate(rows) for c,value in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],
                         [('MENS 100% LINEN WOVEN SHIRT',2),('63% VISCOSE RAYON 37% POLYAMIDE WOVEN SHIRT',1)])

    def test_net_weight_requires_a_unique_explicit_positive_kg_value(self):
        for text,value in [('N.W. 2.7 KGS',2.7),('NET WEIGHT: 1.125 KG',1.125),
                           ('WEIGHT 2.4 KGS',None),('N.W. 0 KG',None),
                           ('NET WEIGHT 7 LBS',None),('NW 2 KG NW 3 KG',None)]:
            self.assertEqual(_extract_net_weight(text),value)
        data=parse_result(OCRResult(content='NET WEIGHT 1.2 KG'),Path('new.pdf'))
        self.assertIsNone(data.net_weight_kg)

    def test_explicit_goods_end_material_context_and_numbers_survive_without_units(self):
        rows=[['PARTICULARS','QTY'],['100% COTTON WOVEN FABRIC','3 YDS'],
              ['SIZE STICKER','2 PCS'],['TRIM CARD','1']]
        cells=[OCRTableCell(r,c,value) for r,row in enumerate(rows) for c,value in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('new.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('100% COTTON WOVEN FABRICS',3,'YDS'),('SIZE STICKER',2,'PCS'),('TRIM CARD',1,'PCS')])

    def test_quantity_header_supplies_only_explicit_unit(self):
        cells=[OCRTableCell(0,0,'DESCRIPTION'),OCRTableCell(0,1,'QUANTITY (YARDS)'),
               OCRTableCell(1,0,'FABRIC'),OCRTableCell(1,1,'12.5')]
        data=parse_result(OCRResult(tables=[OCRTable(cells,2,2)]),Path('new.pdf'))
        self.assertEqual((data.items[0].quantity,data.items[0].unit),(12.5,'YDS'))

    def test_conflicting_identifiers_choose_one_but_repeated_packages_are_not_guessed(self):
        from src.foc_extractor.parser import _extract_package_count
        data=parse_result(OCRResult(content='S/1111/27 S/2222/27'),Path('27S3333-D.pdf'))
        self.assertEqual(data.invoice_number,'S/1111/27')
        self.assertIsNone(_extract_package_count('1 CARTON\n1 CARTON'))
        self.assertEqual(_extract_package_count('1 CARTON\nTOTAL 3 PACKAGES'),3)
        data=parse_result(OCRResult(content='1 CARTON',pages=['1 CARTON']),Path('new.pdf'))
        self.assertIsNone(data.package_count)

    def test_quantity_and_unit_are_distinct(self):
        self.assertEqual(_extract_items_from_text('5kg 1 pack'),[])
        self.assertEqual(_extract_items_from_text('5 KGS 2 ROLLS'),[])
        for text,quantity,unit in [('COTTON 200 YDS',200,'YDS'),('LABEL 1,234.5 PCS',1234.5,'PCS'),('MOULD 5 SETS',5,'SETS')]:
            with self.subTest(text=text):
                item=_extract_items_from_text(text)[0]
                self.assertEqual((item.quantity,item.unit),(quantity,unit))

    def test_valid_and_ambiguous_dates(self):
        self.assertEqual(_extract_export_date('EXPORT DATE: 2027-10-15'),'2027-10-15')
        self.assertIsNone(_extract_export_date('EXPORT DATE: 2027-02-31'))
        self.assertEqual(_extract_export_date('DATE OF EXPORT: 10/13/2027'),'2027-10-13')
        self.assertIsNone(_extract_export_date('DATE OF EXPORT: 10/09/2027'))
        self.assertIsNone(_extract_export_date('DATE OF EXPORT: 31/02/2027'))
        self.assertEqual(_extract_export_date('DATE OF EXPORTATION: 15-SEP,2027'),'2027-09-15')
        self.assertIsNone(_extract_export_date('PACKING DATE: 15-SEP,2027'))
        self.assertIsNone(_extract_export_date('no date'))
        self.assertEqual(_extract_export_date('PACKING DATE: 12-OCT-2027\nDATE OF EXPORT: 15-OCT-2027'),'2027-10-15')
        self.assertIsNone(_extract_export_date('DATE OF EXPORT: 15-OCT-2027\nDATE OF EXPORT: 16-OCT-2027'))
        self.assertIsNone(_extract_export_date('DATE OF EXPORT:\nPACKING DATE: 15-OCT-2027'))
        self.assertEqual(_extract_export_date('DATE OF EXPORT:\n15-OCT-2027'),'2027-10-15')
        self.assertEqual(_extract_export_date('ON/ABT OCT 15, 2027'),'2027-10-15')

    def test_export_dates_handle_punctuation_without_ignoring_conflicts(self):
        self.assertEqual(_extract_export_date('DATE OF EXPORTATION: 07 OCT. 2027'),'2027-10-07')
        self.assertEqual(_extract_export_date('ON / ABT. OCT. 07, 2027'),'2027-10-07')
        self.assertEqual(_extract_export_date('EXPORT DATE: 07 OCT. 2027\nEXPORT DATE: 2027-10-07'),'2027-10-07')
        for other in ('10/09/2027','2027-02-31','2027-10-08'):
            with self.subTest(other=other):
                self.assertIsNone(_extract_export_date('EXPORT DATE: 2027-10-07\nEXPORT DATE: '+other))

    def test_packing_date_fallback_uses_first_dated_packing_page(self):
        def parsed(pages):
            return parse_result(OCRResult(content='\n'.join(pages),pages=pages),Path('anonymous.pdf'))
        dated='PACKING LIST\nDate: 13-Oct-27'
        data=parsed([dated,'PACKING LIST\nDate: 10/13/2027'])
        self.assertEqual(data.export_date,'2027-10-13')
        self.assertTrue(any('first dated PDF packing-list page' in w for w in data.warnings))
        self.assertEqual(parsed([dated,'EXPORT DATE: 15-Oct-27']).export_date,'2027-10-15')
        self.assertEqual(parsed(['PACKING LIST\nDate: 09-Oct-27','PACKING LIST\nDate: 10/09/2027']).export_date,'2027-10-09')
        self.assertEqual(parsed(['PACKING LIST\nDate: 13-0ct-27',dated]).export_date,'2027-10-13')
        self.assertEqual(parsed([dated,'PACKING LIST\nDate: 14-Oct-27']).export_date,'2027-10-13')
        self.assertEqual(parsed(['SHIPPING INSTRUCTIONS','PACKING LIST\nDate: 10/06/2027',
                                 'PACKING LIST\nDate: 04-Oct-27']).export_date,'2027-10-06')
        self.assertEqual(parsed(['PACKING LIST\nDate: 10/09/2027']).export_date,'2027-10-09')
        for pages in (['PACKING LIST\nDate: 31-Feb-27'],
                      ['PACKING LIST\nDate: 09-Oct-27\nDate: 10-Oct-27'],
                      ['PACKING LIST\nStyle booked 13-Oct-27'],
                      ['SHIPPING INSTRUCTIONS\nDate: 13-Oct-27'],
                      [dated,'EXPORT DATE: 2027-02-31'],
                      [dated,'EXPORT DATE: 15-Oct-27\nEXPORT DATE: 16-Oct-27']):
            with self.subTest(pages=pages):self.assertIsNone(parsed(pages).export_date)

    def test_complete_numeric_tokens_and_composition(self):
        for value,expected in [('7,5',7.5),('1,234.5',1234.5),('1.234,5',1234.5)]:
            with self.subTest(value=value):
                self.assertEqual(_extract_items_from_text(f'COTTON {value} YDS')[0].quantity,expected)
                self.assertEqual(_extract_gross_weight(f'G.W. {value} KGS'),expected)
        self.assertEqual(_extract_items_from_text('COTTON -7 YDS'),[])
        self.assertIsNone(_material_heading('100% COTTON 5% UNKNOWN WOVEN'))
        self.assertIsNone(_material_heading('5% UNKNOWN 100% COTTON WOVEN'))
        self.assertEqual(_material_heading('STYLE SHIRT\n100% COTTON DENIM\nSHRINKAGE: 3%x3%', 'WOVEN'),'100% COTTON WOVEN FABRICS')
        self.assertEqual(_clean_material_description('9.5MM RIVET'),'9.5MM RIVET')
        self.assertEqual(_material_heading('52% BCI COTTON 48% RECYCLE POLYESTER','WOVEN'),
                         '52% COTTON 48% RECYCLED POLYESTER WOVEN FABRICS')
        self.assertEqual(_material_heading('100% COTTON (BCl)','WOVEN'),'100% COTTON WOVEN FABRICS')

    def test_merged_description_and_source_rows_survive_aggregation(self):
        rows=[['PARTICULARS','QTY'],['100% COTTON WOVEN FABRICS',''],['','10 YDS'],['BLUE','2 YDS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('100% COTTON WOVEN FABRICS',12)])
        self.assertEqual(data.items[0].source_page,1)
        self.assertEqual(len(data.items[0].source_refs),2)

    def test_late_header_and_explicit_item_column(self):
        rows=[['PACKING LIST'],[''],['NON MUTILATED'],[''],
              ['PARTICULARS','ITEM','QTY','WEIGHT KGS'],
              ['JACKET STYLE ABC\nSHANK BUTTON X 3 GROSS\nDIE MOULD X 2 SETS','SHANK BUTTON\nDIE MOULD','3 GROSS +\n2 SETS','4 KGS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],[('SHANK BUTTON',3,'GROSS'),('DIE MOULD',2,'SETS')])
        self.assertIsNone(data.gross_weight_kg)

    def test_multiline_garments_keep_quantities_with_compositions(self):
        rows=[['PARTICULARS','QTY'],['STYLE ABC SHIRT\n100% LINEN WOVEN SHIRT\n#50\nSTYLE DEF SHIRT\n60% VISCOSE 40% COTTON WOVEN SHIRT\n#30','3 PCS\n2 PCS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('100% LINEN WOVEN SHIRT',3),('60% VISCOSE 40% COTTON WOVEN SHIRT',2)])

    def test_header_only_table_does_not_suppress_text(self):
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY')]
        data=parse_result(OCRResult(tables=[OCRTable(cells,1,2)],pages=['COTTON 10 YDS']),Path('unseen.pdf'))
        self.assertEqual(data.items[0].quantity,10)

    def test_unparsed_table_is_recovered_without_counting_footer_annotations(self):
        from src.foc_extractor.ocr_engine import OCRWord
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'BUTTON'),OCRTableCell(1,1,'2 PCS')]
        words=[OCRWord('BUTTON 2 PCS',.99,10,30,90,40),OCRWord('ZIPPER 3 PCS',.99,10,130,90,140),
               OCRWord('IF HAVE 12 PCS',.99,10,230,90,240)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,2,2,bbox=[0,0,100,100]),OCRTable(bbox=[0,110,100,200])],
                                   words=words,pages=['BUTTON 2 PCS\nZIPPER 3 PCS']),Path('new.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('BUTTON',2),('ZIPPER',3)])

    def test_garment_after_composition_is_not_converted_to_fabric(self):
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'53% VISCOSE 47% COTTON WOMENS WOVEN BLOUSE'),OCRTableCell(1,1,'1 PCS')]
        data=parse_result(OCRResult(tables=[OCRTable(cells,2,2)]),Path('new.pdf'))
        self.assertEqual(data.items[0].description,'53% VISCOSE 47% COTTON WOMENS WOVEN BLOUSE')
        from src.foc_extractor.parser import _material_heading
        self.assertIsNone(_material_heading('Cotton blouse WOMENS WOVEN 53% VISCOSE 47% COTTON'))
        self.assertEqual(_material_heading('88% Cotton 12% Linen75x54','WOVEN'),'88% COTTON 12% LINEN WOVEN FABRICS')

    def test_cartons_require_label(self):
        self.assertIsNone(_extract_carton_range('STYLE S3-S27'))
        self.assertIsNone(_extract_carton_range('C/NO. P09-P01'))
        self.assertEqual(_extract_carton_range('C/NO. E01-E13\nC/NO. B01'),'E01-E13, B01')
        self.assertEqual(_extract_carton_range('CINO. P1O P18'),'P10-P18')

    def test_explicit_packages_are_not_overwritten(self):
        data=parse_result(OCRResult(content='TOTAL 15 PACKAGES\nC/NO. E01-E01'),Path('arbitrary.pdf'))
        self.assertEqual(data.package_count,15)
        self.assertTrue(any('conflicts' in w for w in data.warnings))

    def test_single_packing_table_counts_bare_numbers_and_rolls(self):
        for entries,expected in [(['1'],1),(['1 Roll','2 Rolls'],3),(['1 Roll','UNREADABLE'],None)]:
            rows=[['PARTICULARS','QTY','No of package / rolls']]+[
                [f'ITEM {i}','2 PCS',value] for i,value in enumerate(entries)]
            cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
            table=OCRTable(cells,len(rows),3)
            data=parse_result(OCRResult(tables=[table],pages=['PACKING LIST']),Path('anonymous.pdf'))
            self.assertEqual(data.package_count,expected)
            data=parse_result(OCRResult(tables=[table,table],pages=['PACKING LIST']),Path('anonymous.pdf'))
            self.assertEqual(data.package_count,expected)

    def test_empty_ocr_does_not_fabricate_data(self):
        data=parse_result(OCRResult(),Path('arbitrary.pdf'))
        self.assertEqual(data.items,[])
        for field in ['invoice_number','export_date','package_count','gross_weight_kg','total_value']:
            self.assertIsNone(getattr(data,field))

    def test_garments_and_multiword_materials_survive(self):
        self.assertEqual(_clean_material_description('MENS 100% LINEN WOVEN SHIRTS'),'MENS 100% LINEN WOVEN SHIRTS')
        desc='68% COTTON 28% RECYCLED POLYESTER 3% RAYON 1% SPANDEX WOVEN FABRICS'
        self.assertEqual(_clean_material_description(desc),desc)

    def test_aggregation_uses_real_unit(self):
        items=_aggregate_items([LineItem('COTTON',10,'YDS'),LineItem('COTTON',20,'YDS'),LineItem('COTTON',2,'PCS')])
        self.assertEqual([(i.quantity,i.unit) for i in items],[(30,'YDS'),(2,'PCS')])

    def test_table_columns_exclude_metadata_and_keep_first_row(self):
        cells=[OCRTableCell(0,c,t) for c,t in enumerate(['BUYER','PARTICULARS','QTY','WEIGHT KGS'])]
        cells += [OCRTableCell(1,c,t) for c,t in enumerate(['BUYER NAME','100% COTTON WOVEN FABRICS','25 YDS','2 KGS'])]
        result=OCRResult(tables=[OCRTable(cells,2,4)],content='PACKING LIST',pages=['PACKING LIST'])
        data=parse_result(result,Path('random.pdf'))
        self.assertEqual(len(data.items),1)
        self.assertEqual(data.items[0].quantity,25)
        self.assertNotIn('BUYER',data.items[0].description)

    def test_filename_is_not_silent_ground_truth(self):
        data=parse_result(OCRResult(),Path('27S9876-D.pdf'))
        self.assertEqual(data.invoice_number,'S/9876/27')
        self.assertTrue(any('filename' in w for w in data.warnings))
        conflicting=parse_result(OCRResult(content='S/1234/28'),Path('27S9876-D.pdf'))
        self.assertEqual(conflicting.invoice_number,'S/1234/28')
        self.assertEqual(_extract_gross_weight('SHIPPER PACKAGES app . 56 KGS'),56)

    def test_date_above_carton_label_is_not_package_count(self):
        data=parse_result(OCRResult(content='DATE 15 SEP 2027\nCARTONS'),Path('random.pdf'))
        self.assertIsNone(data.package_count)

    def test_color_rows_inherit_explicit_material_and_fabric_type(self):
        rows=[['PARTICULARS','QTY','WOVEN / KNIT'],
              ['100% NYLON','','WOVEN'],['BLUE','11 YDS',''],['RED','13 YDS',''],
              ['100% COTTON SHIRT','2 PCS','']]
        cells=[OCRTableCell(r,c,value) for r,row in enumerate(rows) for c,value in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),3)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('100% NYLON WOVEN FABRICS',24,'YDS'),('100% COTTON SHIRT',2,'PCS')])

    def test_material_without_fabric_type_does_not_turn_colors_into_products(self):
        rows=[['PARTICULARS','QTY'],['100% NYLON',''],['BLUE','2 PCS'],['RED','3 PCS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('new.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],[('100% NYLON',5,'PCS')])

    def test_repeated_sender_keeps_merged_composition_but_new_sender_resets_it(self):
        rows=[['SENDER','PARTICULARS','QTY','WOVEN / KNIT'],
              ['A','100% COTTON','10 YDS','WOVEN'],['A','COLOR RED','20 YDS','WOVEN'],
              ['B','UNKNOWN GOODS','3 PCS','']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('new.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('100% COTTON WOVEN FABRICS',30),('UNKNOWN GOODS',3)])
        self.assertEqual(_material_heading('62% COTTON 38% POLYAMIDE / 5X5% SHRINKAGE','WOVEN'),
                         '62% COTTON 38% POLYAMIDE WOVEN FABRICS')

    def test_unlabelled_final_sum_is_not_added_to_merged_goods(self):
        for final,quantity in [('30 YDS',30),('5 YDS',35)]:
            rows=[['PARTICULARS','QTY'],['100% COTTON WOVEN FABRICS','20 YDS'],['','10 YDS'],['',final]]
            cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
            data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('new.pdf'))
            self.assertEqual(data.items[0].quantity,quantity)

    def test_narrow_ocr_repairs_are_flagged_and_ambiguous_digits_rejected(self):
        rows=[['PARTICULARS','QTY'],['LABEL','Ipc'],['CLOTH','9vds'],['OTHER','Zyds']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),2)]),Path('new.pdf'))
        self.assertEqual([(i.quantity,i.unit) for i in data.items],[(1,'PCS'),(9,'YDS'),(None,'YDS')])
        self.assertTrue(any('normalized OCR' in w for w in data.warnings))
        self.assertTrue(any('unresolved quantity' in w for w in data.warnings))

    def test_damaged_header_uses_neighboring_columns_not_row_totals(self):
        rows=[['PARIICULARS','90','WEIGHT KGS','No of package'],
              ['100% COTTON WOVEN FABRICS','25 vds','7 KGS','1 ROLL'],
              ['','', '','2027']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,len(rows),4)]),Path('new.pdf'))
        self.assertEqual([(i.quantity,i.unit) for i in data.items],[(25,'YDS')])
        self.assertEqual(data.package_count,1)
        data=parse_result(OCRResult(content='C/NO. A01-A04',tables=[OCRTable(cells,len(rows),4)]),Path('new.pdf'))
        self.assertEqual(data.package_count,4)

    def test_shipping_marks_prioritize_consignee_over_incidental_mentions(self):
        data=parse_result(OCRResult(content='To: EGMCL-FOC\nPEARL BUTTONS'),Path('new.pdf'))
        self.assertEqual(data.consignee,'EPIC GARMENTS MANUFACTURING CO. LTD.')

    def test_known_company_address_fallback_and_factory_units(self):
        for header in ('To: EGMCL 2 -FABRIC','EGMCL-2 FOC',
                       'To: EPIC GARMENTS MANUFACTURING CO. LTD. (UNIT-2)'):
            data=parse_result(OCRResult(content=header+'\nPACKING LIST'),Path('anonymous.pdf'))
            self.assertIn('UNIT-2',data.consignee)
            self.assertIn('000320579-0403',data.consignee_address)
            self.assertNotIn('000322109-1402',data.consignee_address)
        for header in ('To: EGMCL-FOC','To: CIPL-FOC','To: THE ROSE DRESSES LTD'):
            data=parse_result(OCRResult(content=header+'\nPACKING LIST'),Path('anonymous.pdf'))
            self.assertTrue(data.consignee_address)
            self.assertIn('BIN',data.consignee_address)
        for header in ('To: EGMCL 3 FOC','To: EGMCL 20 FOC',
                       'To: UNKNOWN FACTORY\nPACKING LIST\nPEARL BUTTONS'):
            data=parse_result(OCRResult(content=header),Path('anonymous.pdf'))
            self.assertIsNone(data.consignee_address)

    def test_source_address_and_bin_take_priority_over_directory(self):
        from unittest.mock import patch
        source='GREEN TEXTILE LIMITED\nNEW FACTORY ROAD\nBIN: 123456789-0123\nTel no.'
        with patch('src.foc_extractor.parser._consignee_region',return_value=source):
            data=parse_result(OCRResult(),Path('anonymous.pdf'))
        self.assertEqual(data.consignee_address,'NEW FACTORY ROAD\nBIN: 123456789-0123')
        self.assertNotIn('000830659-0104',data.consignee_address)
        with patch('src.foc_extractor.parser._consignee_region',return_value='GREEN TEXTILE LIMITED\nNEW FACTORY ROAD'):
            data=parse_result(OCRResult(),Path('anonymous.pdf'))
        self.assertIn('NEW FACTORY ROAD',data.consignee_address)
        self.assertIn('000830659-0104',data.consignee_address)
