from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor import ocr_engine as engine
from src.foc_extractor.ocr_engine import OCRResult,OCRWord,OCRTable,OCRTableCell
from src.foc_extractor.parser import parse_result
from src.foc_extractor.processing_evidence import observed


class ShippedTableTests(unittest.TestCase):
    def source(self):
        image=Image.new('RGB',(2400,3500),'white')
        draw=ImageDraw.Draw(image)
        for x in (80,300,700,1250,1450,1650,1940,2125,2320):
            draw.line((x,1680,x,1850),fill='black',width=2)
        for y in (1680,1760,1805,1850):draw.line((80,y,2320,y),fill='black',width=2)
        def word(text,x,y,width=150,height=32):
            return OCRWord(text,.99,x,y,x+width,y+height)
        words=[word('DESCRIPTION',850,1690),word('SHIPPED',1270,1690),
               word('QTY.',1270,1725,70),word('(UNIT)',1490,1725),
               word('BALANCE',1690,1690),word('ORDERED',2140,1690),
               word('QTY.',2140,1725,70),
               word('SHANK BUTTON DIE MOULD',720,1767,470),
               word('1',1400,1767,30),word('Set (2Pcs)',1470,1767),
               word('RIVET DIE MOULD',720,1810,400),
               word('5 Set (2Pcs)',1410,1810,220),
               word('99',2160,1767,50),word('88',2160,1810,50),
               word('777',1700,1767,80),word('Total:',300,1880),
               word('999',750,1880),word('Total Gross Weight: 9 KG',300,1950,800),
               word('SHORT SHIPMENT OF',300,2060,800),word('PHANTOM 888 PCS',700,2140,500)]
        # Short letter strokes must not become false column rules in the cropped grid.
        for x in range(730,1100,20):draw.line((x,1772,x,1795),fill='black',width=2)
        return image,OCRResult(content='PACKING LIST',pages=['PACKING LIST'],words=words,
                               total_pages=1,backend='paddle',table_version=6,
                               page_transforms=[{'rotation':0,'skew':0}])

    def test_shipped_columns_exclude_order_balance_packing_factors_and_footer(self):
        image,ocr=self.source()
        with patch.object(engine,'_cached_page_image',return_value=image) as render:
            self.assertTrue(engine._recover_shipped_tables(ocr,Path('anonymous.pdf')))
            self.assertFalse(engine._recover_shipped_tables(ocr,Path('anonymous.pdf')))
            render.assert_called_once()
        data=parse_result(ocr,Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('DIE MOULD (SHANK)',1,'SETS'),('DIE MOULD (RIVET)',5,'SETS')])
        self.assertEqual([i.source_refs for i in data.items],[['1:1:2'],['1:1:3']])
        from src.foc_extractor.packages import _package_box
        from src.foc_extractor.parser import _table_fields
        self.assertIsNone(_package_box(ocr,ocr.tables[0],*_table_fields(ocr.tables[0])))
        self.assertTrue(all(c.bbox for c in ocr.tables[0].cells))
        self.assertTrue(all(1680<c.bbox[1]<1851 for c in ocr.tables[0].cells if c.row_index))

    def test_missing_headers_boundaries_and_existing_tables_do_not_guess(self):
        image,original=self.source()
        for excluded in ('(UNIT)','Total:','DESCRIPTION'):
            ocr=deepcopy(original)
            ocr.words=[w for w in ocr.words if w.text!=excluded and
                       (excluded!='Total:' or w.text!='SHORT SHIPMENT OF')]
            with patch.object(engine,'_cached_page_image',return_value=image):
                self.assertFalse(engine._recover_shipped_tables(ocr,Path('anonymous.pdf')))
        ocr=deepcopy(original)
        ocr.tables=[OCRTable([OCRTableCell(0,0,'DESCRIPTION'),OCRTableCell(0,1,'QTY'),
                             OCRTableCell(1,0,'LABEL'),OCRTableCell(1,1,'10 PCS')],2,2)]
        before=deepcopy(ocr)
        with patch.object(engine,'_cached_page_image') as render:
            self.assertFalse(engine._recover_shipped_tables(ocr,Path('anonymous.pdf')))
            render.assert_not_called()
        self.assertEqual(ocr,before)

    def test_fresh_and_old_aggregate_cache_follow_the_same_recovery(self):
        image,ocr=self.source()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pdf=root/'anonymous.pdf';pdf.write_bytes(b'source')
            key=hashlib.sha256(b'sourcepaddle-mobile-v1:3.7.0:3.2.0:None:300').hexdigest()
            cache=root/'cache';cache.mkdir()
            with patch.object(engine,'analyze_with_paddle',return_value=deepcopy(ocr)) as sdk, \
                 patch.object(engine,'_cached_page_image',return_value=image):
                fresh=engine.analyze_pdf(pdf,cache_dir=cache)
                sdk.assert_called_once()
            (cache/(key+'.json')).write_text(json.dumps(asdict(ocr)))
            with patch.object(engine,'analyze_with_paddle') as sdk, \
                 patch.object(engine,'_cached_page_image',return_value=image) as render:
                cached=engine.analyze_pdf(pdf,cache_dir=cache)
                repeated=engine.analyze_pdf(pdf,cache_dir=cache)
                sdk.assert_not_called();render.assert_called_once()
            self.assertEqual(fresh,cached)
            self.assertEqual(cached,repeated)

    def test_superseded_unrecognized_grid_does_not_duplicate_goods(self):
        image,ocr=self.source()
        ocr.tables=[OCRTable([OCRTableCell(0,0,'ORDERED')],1,1,0,[80,1680,2320,1850])]
        with patch.object(engine,'_cached_page_image',return_value=image):
            self.assertTrue(engine._recover_shipped_tables(ocr,Path('anonymous.pdf')))
        self.assertEqual(len(ocr.tables),1)
        self.assertEqual(sum(i.quantity for i in parse_result(ocr,Path('anonymous.pdf')).items),6)

    def test_page_dispositions_include_unresolved_and_unprocessed_pages(self):
        image,ocr=self.source()
        with patch.object(engine,'_cached_page_image',return_value=image):
            engine._recover_shipped_tables(ocr,Path('anonymous.pdf'))
        ocr.pages+=['SHIPPER\nCONSIGNEE','PACKING LIST','UNIDENTIFIED ATTACHMENT','']
        ocr.total_pages=6
        events=[]
        data=observed(parse_result)(ocr,Path('anonymous.pdf'),observer=lambda event,**kw:events.append(event))
        coverage=next(e['evidence'] for e in events if e.get('field')=='page_coverage')
        self.assertEqual([p['status'] for p in coverage],['goods_extracted','shipment_cover',
                         'packing_list_unresolved','unclassified','unreadable','not_processed'])
        self.assertEqual(coverage[0]['goods_rows'],2)
        self.assertTrue(any('Page 6: not processed' in w for w in data.warnings))
        ocr.tables[0].cells[-1].content='unreadable'
        events.clear()
        observed(parse_result)(ocr,Path('anonymous.pdf'),observer=lambda event,**kw:events.append(event))
        coverage=next(e['evidence'] for e in events if e.get('field')=='page_coverage')
        self.assertEqual(coverage[0]['status'],'goods_partial')
        self.assertEqual(coverage[0]['unresolved_quantities'],1)


if __name__=='__main__':unittest.main()
