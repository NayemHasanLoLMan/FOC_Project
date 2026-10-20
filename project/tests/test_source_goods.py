import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell, OCRWord
from src.foc_extractor.parser import parse_result, _clean_material_description, _material_heading


class SourceGoodsTests(unittest.TestCase):
    def parse(self, rows, words=(), boxes=None, bbox=None):
        cells=[OCRTableCell(r,c,v,bbox=(boxes or {}).get((r,c)))
               for r,row in enumerate(rows) for c,v in enumerate(row) if v]
        return parse_result(OCRResult(tables=[OCRTable(cells,len(rows),max(map(len,rows)),bbox=bbox)],
                                      words=list(words)),Path('unseen-shipment.pdf'))

    def test_fab_annotation_classifies_continuations_without_touching_other_products(self):
        rows=[['PARTICULARS','QTY','WEIGHT'],['100% NYLON','',''],
              ['BLUE','1 PCS','FAB UNCLEAR'],['RED','2 PCS',''],['SHANK BUTTON','3 PCS','']]
        data=self.parse(rows)
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('FABRIC SAMPLES',3,'PCS'),('SHANK BUTTON',3,'PCS')])
        self.assertTrue(any('broad fabric-sample' in w for w in data.warnings))

    def test_sample_notes_do_not_convert_pack_counts_to_pieces(self):
        data=self.parse([['PARTICULARS','QTY','WEIGHT'],
                         ['BULK FABRIC BLANKET\nOTHER BOOKING TEXT','4 PACKS','FAB UNCLEAR'],
                         ['TAPER CARD\nOTHER BOOKING TEXT','2 PACKS','']])
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('BULK FABRIC BLANKET',4,'PACKS'),('TAPER CARD',2,'PACKS')])

    def test_handloom_sample_context_beats_shirt_booking_words(self):
        data=self.parse([['PARTICULARS','QTY','WEIGHT'],
                         ['HANDLOOM FOR NEW SHIRT - 60% COTTON 40% POLYESTER','2 PCS','FAB UNCLEAR'],
                         ['NEW FABRIC - 100% NYLON','3 PCS','']])
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('FABRIC SAMPLES',5)])

    def test_counted_cards_get_contextual_pcs_but_materials_stay_unknown(self):
        data=self.parse([['PARTICULARS','QTY'],['TRIM CARD',''],['STYLE-A','1'],['STYLE-B','1'],
                         ['100% COTTON','3'],['FABRIC CARD','1.5']])
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('TRIM CARD',2,'PCS'),('100% COTTON',3,None),('FABRIC CARD',1.5,None)])
        self.assertTrue(any('PCS inferred' in w for w in data.warnings))

    def test_late_merged_woven_label_applies_without_a_percentage_guess(self):
        data=self.parse([['SENDER','PARTICULARS','QTY','WOVEN / KNIT'],
                         ['','94% COTTON 6% STRETCH','', ''],['','KHAKI','7 YDS',''],
                         ['MILL','', '', 'WOVEN']])
        self.assertEqual(data.items[0].description,'94% COTTON 6% STRETCH WOVEN FABRICS')
        data=self.parse([['PARTICULARS','QTY','WOVEN / KNIT'],
                         ['SHELL FABRIC - SAMPLE 000 COTTON','5 YDS','WOVEN']])
        self.assertEqual(data.items[0].description,'COTTON WOVEN FABRICS')
        self.assertNotIn('100%',data.items[0].description)

    def test_source_garment_glyphs_and_gender_do_not_become_fabric(self):
        self.assertEqual(_clean_material_description('LADIES 10OZO COTTON WOVEN DRESS'),
                         'LADIES 100% COTTON WOVEN DRESS')
        self.assertEqual(_clean_material_description('7men 100% cotton woven pants'),
                         'MEN 100% COTTON WOVEN PANTS')
        for noun in ('DRESS','DRESSES','SHIRT','PANTS','BLOUSE','JACKET'):
            self.assertIsNone(_material_heading('LADIES 100% COTTON WOVEN '+noun))
        self.assertEqual(_clean_material_description('MEATAL SNAP'),'METAL SNAP')
        self.assertEqual(_clean_material_description('SHANK & RIVET - 2G EACH ITEM & COLOR'),'SHANK & RIVET')

    def test_numbered_garments_split_only_with_inline_quantities_and_conserved_total(self):
        for total, split in [('2 PCS',True),('3 PCS',False)]:
            rows=[['SENDER','PARTICULARS','','','QTY'],
                  ['A','KIPS 1OOT OTTON WOVEN\n1. NEW-123 (DENIM JACKET)\n2. NEW-456 (MINI DRESS)',
                   'I PC','1 PC',total]]
            data=self.parse(rows)
            if split:
                self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                    [('KIDS 100% COTTON WOVEN JACKET',1,'PCS'),('KIDS 100% COTTON WOVEN DRESS',1,'PCS')])
            else:
                self.assertEqual(len(data.items),1)
                self.assertEqual(data.items[0].quantity,3)

    def test_matching_bottom_annotation_is_bounded_and_product_consistent(self):
        rows=[['PURPOSE','PARTICULARS','QTY'],['SAMPLE','STYLE: XYZ MAXI DRESS','1 PCS']]
        boxes={(1,0):[0,10,100,100],(1,1):[100,10,400,100],(1,2):[400,10,500,100]}
        for label,x,y,expected in [('LADIES 10OZO COTTON WOVEN DRESS',110,105,'LADIES 100% COTTON WOVEN DRESS'),
                                   ('LADIES 10OZO COTTON WOVEN DRESS',110,300,'MAXI DRESS'),
                                   ('LADIES 10OZO COTTON WOVEN DRESS',600,105,'MAXI DRESS'),
                                   ('LADIES 10OZO COTTON WOVEN SHIRT',110,105,'MAXI DRESS')]:
            words=[OCRWord(label,.95,x,y,x+280,y+25)]
            data=self.parse(rows,words,boxes,[0,0,500,100])
            self.assertEqual(data.items[0].description,expected)

    def test_raw_card_specificity_refines_item_label(self):
        data=self.parse([['PARTICULARS','ITEM','QTY'],
                         ['FABRIC SWATCH CARD FOR HANDFEEL','FABRIC SWATCH','1 SET']])
        self.assertEqual([(i.description,i.unit) for i in data.items],[('FABRIC SWATCHES CARD','SETS')])

    def test_handwritten_trim_category_applies_only_to_the_related_split_parts(self):
        data=self.parse([['PARTICULARS','QTY','WEIGHT'],
                         ['FABRIC HANGER\nFAP UNCLEAR\nMF PART CARD\nEMBY MF PART CARD',
                          '2 PCS\n1 PC\n2 PCS','2 KG\nTRM CARD']])
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('FABRIC SAMPLES',2,'PCS'),('TRIM CARD',3,'PCS')])


if __name__=='__main__':
    unittest.main()
