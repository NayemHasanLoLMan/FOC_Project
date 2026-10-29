from copy import deepcopy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch

import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.goods_grouping import summarize_goods
from src.foc_extractor.models import FOCData,LineItem
from src.foc_extractor.processing_evidence import observed
from src.foc_extractor.ocr_engine import OCRResult
from src.foc_extractor.pipeline import run


class GoodsGroupingTests(unittest.TestCase):
    def data(self,items,region='JORDAN'):
        return FOCData(source_file='unseen.pdf',template_type=region,items=items)

    def test_garment_styles_share_composition_but_material_construction_and_wearer_stay_distinct(self):
        items=[LineItem('LADIES 100% COTTON KNIT FLEECE '+style+' (NON-MUTILATED)',quantity,'PCS')
               for style,quantity in [('CREW',1),('HOODIE',1),('FULL ZIP HOODIE',1),('HALF ZIP HOODIE',1),
                                      ('STRAIGHT LEG PANTS',2),('JOGGER',1),('BARREL SWEATPANTS',1)]]
        items += [LineItem("MEN'S 88%RECYCLED POLYESTER 12% SPANDE KNIT "+style+' (NON-MUTILATED)',1,'PCS')
                  for style in ('SS TEE','LONG SLEEVE TEE','SS POLO','LONG POLO','TANK TOP')]
        other=[LineItem('LADIES 100% COTTON WOVEN PANTS',2,'PCS'),
               LineItem("MEN'S 100% COTTON KNIT JOGGER",3,'PCS'),
               LineItem('LADIES 99% COTTON 1% ELASTANE KNIT PANTS',4,'PCS'),
               LineItem('100% COTTON KNIT FABRICS',5,'YDS')]
        data=self.data(items+deepcopy(other));summarize_goods(data)
        self.assertEqual(len(data.items),6)
        self.assertEqual((data.items[0].description,data.items[0].quantity),('LADIES 100% COTTON KNIT (NON-MUTILATED)',8))
        self.assertEqual((data.items[1].description,data.items[1].quantity),("MEN'S 88% RECYCLED POLYESTER 12% SPANDEX KNIT (NON-MUTILATED)",5))
        self.assertEqual(data.items[2:],other)

    def test_trim_categories_and_evidence_backed_unit_recovery(self):
        items=[LineItem('THREAD TEX24',15,'CONES',source_refs=['1:1:1']),
               LineItem('THREAD TEX27 / 402',15,'CONE',source_refs=['1:1:2']),
               LineItem('14L 4 HOLE BUTTON COL OFF WHITE',1,'GRS'),LineItem('18L 4 HOLE BUTTON COL WHITE',3,'GROSS'),
               LineItem('1/4 INCH BLACK ELASTIC',30,'YDS'),LineItem('2 INCH WHITE ELASTIC',60,'YDS'),
               LineItem('WOVEN MAIN LABEL',60,'PCS'),LineItem('WOVEN SIZE LABEL',60,'PCS'),
               LineItem('FABRIC SWATCHES',60,'PCS',source_refs=['2:2:1']),
               LineItem('88% POLYESTER 12% SPANDEX FABRIC SWATCHES',1,None,source_refs=['3:3:1'])]
        data=self.data(items);events=[]
        observed(summarize_goods)(data,observer=lambda event,**kw:events.append(event))
        self.assertEqual([(it.description,it.quantity,it.unit) for it in data.items],
                         [('THREAD',30,'CONES'),('BUTTON',4,'GROSS'),('ELASTIC',90,'YDS'),
                          ('LABEL',120,'PCS'),('FABRIC SWATCHES',61,'PCS')])
        evidence=next(e['evidence'] for e in events if e.get('field')=='goods_grouping')
        self.assertEqual(len(evidence['source_items']),10)
        self.assertEqual(evidence['recovered_units'][0]['supporting_refs'],['2:2:1'])
        self.assertIsNone(evidence['source_items'][-1]['unit'])
        self.assertEqual(data.items[-1].source_refs,['2:2:1','3:3:1'])

    def test_different_units_codes_prices_origins_and_unknown_quantities_are_not_combined(self):
        base=LineItem('THREAD TEX24',2,'CONES',hs_code='00123',unit_price=.1,origin_country='CHINA')
        items=[base]
        for field,value in [('unit','PCS'),('hs_code','00456'),('unit_price',.2),('origin_country','VIETNAM'),('quantity',None)]:
            item=deepcopy(base);setattr(item,field,value);items.append(item)
        data=self.data(items);before=deepcopy(items);summarize_goods(data)
        self.assertEqual(data.items,before)

    def test_ambiguous_or_unsupported_units_remain_empty(self):
        for units in [('PCS','SETS',None),(None,None),('G',None)]:
            data=self.data([LineItem('FABRIC SWATCHES',1,unit) for unit in units])
            summarize_goods(data)
            self.assertTrue(any(it.unit is None for it in data.items))
        data=self.data([LineItem('FABRIC SWATCHES',1,'PCS'),LineItem('DIE MOULD',1,None)])
        summarize_goods(data);self.assertIsNone(data.items[-1].unit)

    def test_source_amounts_complete_weights_and_references_are_preserved(self):
        data=self.data([LineItem('THREAD TEX24',10,'CONES',weight_kg=1.2,unit_price=.1,amount=1,
                                source_page=1,source_refs=['1:1:1']),
                        LineItem('THREAD TEX27',20,'CONES',weight_kg=2.3,unit_price=.1,amount=2,
                                source_page=2,source_refs=['2:2:1'])])
        summarize_goods(data);item=data.items[0]
        self.assertEqual((item.quantity,item.amount,item.weight_kg),(30,3,3.5))
        self.assertIsNone(item.source_page);self.assertEqual(item.source_refs,['1:1:1','2:2:1'])
        data=self.data([LineItem('THREAD TEX24',1,'CONES',weight_kg=2),LineItem('THREAD TEX27',1,'CONES')])
        summarize_goods(data);self.assertIsNone(data.items[0].weight_kg)

    def test_new_pipeline_uses_the_same_rule_for_all_three_countries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pdf=root/'unseen.pdf'
            with pymupdf.open() as source:source.new_page();source.save(pdf)
            for region,country in [('BD','Bangladesh'),('INDIA','India'),('JORDAN','Jordan')]:
                data=self.data([LineItem('THREAD TEX24',10,'CONES'),LineItem('THREAD TEX27',20,'CONES')],region)
                data.destination_country=country;data.pages_total=data.pages_processed=1
                with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=OCRResult(pages=['DESTINATION COUNTRY '+country])), \
                     patch('src.foc_extractor.pipeline.parse_result',return_value=data):
                    run(pdf,region=region,output_dir=root/region,local_model=None)
                self.assertEqual(len(data.items),1,region)
                self.assertEqual((data.items[0].description,data.items[0].quantity,data.items[0].unit),('THREAD',30,'CONES'))


if __name__=='__main__':unittest.main()
