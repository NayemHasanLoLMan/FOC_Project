import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.local_vision import transcribe_cell,_accepted_quantity,_quantity_correction_box,resolve_quantities
from src.foc_extractor.ocr_engine import OCRResult,OCRWord,OCRTable,OCRTableCell
from src.foc_extractor.processing_evidence import observed,EvidenceWriteError


class VisionRecoveryTests(unittest.TestCase):
    tags={'models':[{'name':'primary:latest','digest':'one'},{'name':'qwen3.5:4b','digest':'two'}]}
    def response(self,text):return {'done_reason':'stop','message':{'content':json.dumps({'text':text})}}
    def image(self):return Image.new('RGB',(220,180),'white')

    def test_terminal_length_is_diagnostic_cache_never_an_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            bad={'done_reason':'length','message':{'content':'{"text":"99 PCS"}','thinking':'unfinished reasoning'},'eval_count':4096}
            events=[]
            with patch('src.foc_extractor.local_vision._request',side_effect=[self.tags,bad,self.tags]) as request:
                for _ in range(2):
                    result=observed(transcribe_cell)(self.image(),'primary',directory,observer=lambda e,**kw:events.append(e))
                    self.assertIsNone(result[0])
            self.assertEqual(request.call_count,3)
            responses=[e for e in events if e['kind']=='vision_response']
            self.assertEqual([e['cached'] for e in responses],[False,True])
            self.assertFalse(any(e['reusable_answer'] for e in responses))
            self.assertEqual(responses[-1]['raw_thinking'],'unfinished reasoning')
            self.assertEqual(responses[-1]['raw_content'],'{"text":"99 PCS"}')

    def test_unusable_primary_recovers_once_with_separate_model_evidence(self):
        context={'call_id':'original','field':'goods_quantity','source_ref':'1:1:2'};events=[]
        responses=[self.tags,{'done_reason':'length','message':{'content':''}},self.tags,self.response('7 YDS')]
        with patch('src.foc_extractor.local_vision._request',side_effect=responses) as request:
            answer,provenance=observed(transcribe_cell)(self.image(),'primary',context=context,
                accept=lambda a:_accepted_quantity('YDS',a.get('text') if a else None),observer=lambda e,**kw:events.append(e))
        self.assertEqual(answer,{'text':'7 YDS'});self.assertIn('qwen3.5:4b',provenance)
        sent=[e for e in events if e['kind']=='vision_request']
        self.assertEqual([e['configured_model'] for e in sent],['primary','qwen3.5:4b'])
        self.assertNotEqual(sent[0]['call_id'],sent[1]['call_id'])
        self.assertEqual(sent[0]['source_ref'],sent[1]['source_ref'])
        self.assertEqual([call.args[1]['options']['num_predict'] for call in request.call_args_list if call.args[0]=='chat'],[256,256])

    def test_wrong_unit_or_malformed_primary_is_not_silently_accepted(self):
        for first in [self.response('2 PCS'),{'done_reason':'stop','message':{'content':'{bad'}}]:
            with self.subTest(first=first),patch('src.foc_extractor.local_vision._request',side_effect=[self.tags,first,self.tags,self.response('3 YDS')]):
                answer,_=transcribe_cell(self.image(),'primary',accept=lambda a:_accepted_quantity('YDS',a.get('text') if a else None))
            self.assertEqual(answer,{'text':'3 YDS'})

    def test_schema_types_and_extra_properties_are_checked(self):
        for answer in [{'text':123},{'text':'7 PCS','extra':'instruction'}, {}, ['7 PCS']]:
            with self.subTest(answer=answer),patch('src.foc_extractor.local_vision._request',side_effect=[self.tags,{'done_reason':'stop','message':{'content':json.dumps(answer)}}]):
                self.assertIsNone(transcribe_cell(self.image(),'primary')[0])
        schema={'type':'object','properties':{'weight_kg':{'type':['number','null']}},'required':['weight_kg'],'additionalProperties':False}
        for value in (True,float('nan'),float('inf'),9**400):
            with patch('src.foc_extractor.local_vision._request',side_effect=[self.tags,{'done_reason':'stop','message':{'content':json.dumps({'weight_kg':value})}}]):
                self.assertIsNone(transcribe_cell(self.image(),'primary',schema=schema)[0])

    def test_usable_primary_stops_recovery_and_fallback_is_not_duplicated(self):
        for model,text,expected in [('primary','5 PCS',2),('qwen3.5:4b','5 PCS',2),('qwen3.5:4b',None,4)]:
            tags={'models':self.tags['models']+[{'name':'qwen3-vl:latest','digest':'large'}]}
            with patch('src.foc_extractor.local_vision._request',side_effect=[tags,self.response(text),tags,self.response('5 PCS')]) as request:
                transcribe_cell(self.image(),model,accept=lambda a:_accepted_quantity('PCS',a.get('text') if a else None))
            self.assertEqual(request.call_count,expected)

    def corrected(self,readable=False):
        lower='17 YDS' if readable else '17YO5'
        cell=OCRTableCell(1,1,'19 YDS\n'+lower,bbox=[0,0,200,160])
        table=OCRTable([OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),OCRTableCell(1,0,'FABRIC'),cell],2,2)
        ocr=OCRResult(pages=['PACKING LIST'],tables=[table],words=[OCRWord('19 YDS',1,30,30,180,60),OCRWord(lower,.5,40,90,150,130)])
        image=self.image();ImageDraw.Draw(image).line((30,45,180,45),fill='blue',width=4)
        return ocr,cell,image

    def test_only_struck_upper_reading_allows_tight_lower_crop(self):
        ocr,cell,image=self.corrected()
        self.assertEqual(_quantity_correction_box(ocr,cell,image),[32,82,158,138])
        self.assertIsNone(_quantity_correction_box(ocr,cell,self.image()))
        underline=self.image();ImageDraw.Draw(underline).line((30,64,180,64),fill='blue',width=4)
        self.assertIsNone(_quantity_correction_box(ocr,cell,underline))
        ocr.words.append(OCRWord('6 YDS',1,10,140,190,155))
        self.assertIsNone(_quantity_correction_box(ocr,cell,image))

    def test_replacement_is_accepted_only_with_matching_literal_verification(self):
        for numeral,accepted in [('17 YDS',True),('17 YOS',True),('18 YDS',False),('17 PCS',False),(None,False)]:
            ocr,cell,image=self.corrected();events=[]
            with patch('src.foc_extractor.local_vision._cached_page_image',return_value=image),patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[({'text':'17 YDS'},'primary'),({'text':numeral},'literal')]):
                observed(resolve_quantities)(ocr,Path('anonymous.pdf'),'primary',observer=lambda e,**kw:events.append(e))
            self.assertEqual(cell.content,'17 YDS' if accepted else '19 YDS\n17YO5')
            self.assertEqual(next(e for e in events if e['kind']=='vision_decision')['accepted'],accepted)

    def test_readable_two_values_are_not_summed_when_one_is_visibly_struck(self):
        ocr,cell,image=self.corrected(readable=True)
        with patch('src.foc_extractor.local_vision._cached_page_image',return_value=image),patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[({'text':'17 YDS'},'literal'),({'text':'17 YDS'},'literal')]):
            resolve_quantities(ocr,Path('anonymous.pdf'),'primary')
        self.assertEqual(cell.content,'17 YDS')
        ocr,cell,_=self.corrected(readable=True)
        with patch('src.foc_extractor.local_vision._cached_page_image',return_value=self.image()),patch('src.foc_extractor.local_vision.transcribe_cell') as read:
            resolve_quantities(ocr,Path('anonymous.pdf'),'primary')
        read.assert_not_called();self.assertEqual(cell.content,'19 YDS\n17 YDS')

    def test_annotation_only_cells_do_not_request_or_invent_a_quantity(self):
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'INTERLINING'),OCRTableCell(1,1,'FAB SMOOTHES',bbox=[0,0,200,160])]
        with patch('src.foc_extractor.local_vision.transcribe_cell') as read:
            resolve_quantities(OCRResult(tables=[OCRTable(cells,2,2)]),Path('anonymous.pdf'),'primary')
        read.assert_not_called();self.assertEqual(cells[-1].content,'FAB SMOOTHES')

    def test_repeated_bare_unit_is_resolved_without_vision_or_unit_conversion(self):
        from src.foc_extractor.parser import _quantity_text
        for text in ['yds\n15 YDS','15 YDS\nYARDS','YARDS\n15 YDS\nYDS']:
            self.assertEqual(_quantity_text(text),'15 YDS')
        for text in ['PCS\n15 YDS','15 YDS\n15 YDS','15 YDS\nTOTAL']:
            self.assertEqual(_quantity_text(text),text)
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'FABRIC'),OCRTableCell(1,1,'YDS\n15 YDS',bbox=[0,0,200,160])]
        with patch('src.foc_extractor.local_vision.transcribe_cell') as read:
            resolve_quantities(OCRResult(tables=[OCRTable(cells,2,2)]),Path('anonymous.pdf'),'primary')
        read.assert_not_called()

    def test_correction_can_prefer_literal_reader_with_configured_reader_as_recovery(self):
        responses=[self.tags,self.response(None),self.tags,self.response('7 YDS')]
        with patch('src.foc_extractor.local_vision._request',side_effect=responses) as request:
            answer,_=transcribe_cell(self.image(),'primary',prefer_fallback=True,
                                    accept=lambda a:_accepted_quantity('YDS',a.get('text') if a else None))
        self.assertEqual(answer,{'text':'7 YDS'})
        self.assertEqual([call.args[1]['model'] for call in request.call_args_list if call.args[0]=='chat'],['qwen3.5:4b','primary:latest'])

    def test_yard_unit_glyph_repairs_never_change_the_quantity_or_other_text(self):
        from src.foc_extractor.parser import _quantity_text
        for text in ('17YOS','17Y0S','17Y05'):
            self.assertEqual(_quantity_text(text),'17 YDS')
            self.assertTrue(_accepted_quantity('19 YDS\n17Y05',text))
        for text in ('YOS','17 PCS','17Y04','STYLE-Y05'):
            self.assertEqual(_quantity_text(text),text)

    def test_evidence_errors_are_not_recovered_as_model_failures(self):
        def fail(e,**kw):raise OSError('disk full')
        with self.assertRaises(EvidenceWriteError):
            observed(transcribe_cell)(self.image(),'primary',accept=lambda a:True,observer=fail)


if __name__=='__main__':unittest.main()
