import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.local_vision import transcribe_cell,DEFAULT_MODEL
from src.foc_extractor.india import resolve_invoice_number,INVOICE_FALLBACK_MODEL
from src.foc_extractor.ocr_engine import OCRResult,OCRWord

class FastVisionTests(unittest.TestCase):
 def test_short_fields_cap_output_without_changing_user_timeout_or_context(self):
  tags={'models':[{'name':'custom','digest':'one'}]}
  response={'done_reason':'stop','message':{'content':'{"text":"7 PCS"}'}}
  for field,budget in [('invoice_number',256),('goods_quantity',256),('gross_weight_kg',256),('package_count',256),('export_date',256),('goods_description',512),('unrelated',4096)]:
   with self.subTest(field=field),patch('src.foc_extractor.local_vision._request',side_effect=[tags,response]) as call:
    transcribe_cell(Image.new('RGB',(40,20)),'custom',context={'field':field})
    payload=call.call_args.args[1]
    self.assertEqual(payload['options']['num_predict'],budget)
    self.assertEqual(payload['options']['num_ctx'],8192)
    self.assertFalse(payload['think']);self.assertEqual(payload['keep_alive'],0)

 def test_small_reader_first_but_invalid_values_escalate(self):
  tags={'models':[{'name':DEFAULT_MODEL,'digest':'large'},{'name':INVOICE_FALLBACK_MODEL,'digest':'small'}]}
  for first,expected in [('7 YDS',[INVOICE_FALLBACK_MODEL]),('7 PCS',[INVOICE_FALLBACK_MODEL,DEFAULT_MODEL])]:
   responses=[tags,{'done_reason':'stop','message':{'content':json.dumps({'text':first})}},tags,{'done_reason':'stop','message':{'content':'{"text":"7 YDS"}'}}]
   with patch('src.foc_extractor.local_vision._request',side_effect=responses) as request:
    from src.foc_extractor.local_vision import _accepted_quantity
    answer,_=transcribe_cell(Image.new('RGB',(40,20)),DEFAULT_MODEL,context={'field':'goods_description'},accept=lambda a:_accepted_quantity('YDS',a.get('text') if a else None))
    self.assertEqual(answer,{'text':'7 YDS'})
    self.assertEqual([c.args[1]['model'] for c in request.call_args_list if c.args[0]=='chat'],expected)

 def test_corrected_quantity_and_weight_keep_the_configured_reader_first(self):
  tags={'models':[{'name':DEFAULT_MODEL,'digest':'large'},{'name':INVOICE_FALLBACK_MODEL,'digest':'small'}]}
  for field in ['goods_quantity','gross_weight_kg']:
   with patch('src.foc_extractor.local_vision._request',side_effect=[tags,{'done_reason':'stop','message':{'content':'{"text":"7"}'}}]) as request:
    transcribe_cell(Image.new('RGB',(40,20)),DEFAULT_MODEL,context={'field':field},accept=lambda a:bool(a))
    self.assertEqual(request.call_args.args[1]['model'],DEFAULT_MODEL)
    self.assertEqual(request.call_args.args[1]['options']['num_predict'],512)

 def ocr(self):
  return OCRResult(content='SHIPPER',pages=['SHIPPER'],words=[OCRWord('Invoice No.',1,100,100,250,130),OCRWord('6742/29',.5,260,100,450,135)])

 def test_two_views_still_required_and_conflicts_escalate(self):
  for values,number,models in [
   ([{'text':'S/6742/29'},{'serial':'6742','year':'29'}],'S/6742/29',[INVOICE_FALLBACK_MODEL]*2),
   ([{'text':'S/6742/29'},{'serial':'6743','year':'29'},{'text':'S/6742/29'}],'S/6742/29',[INVOICE_FALLBACK_MODEL]*2+[DEFAULT_MODEL]),
   ([{'text':None},{'serial':None,'year':None},{'text':'S/6742/29'}],'S/6742/29',[INVOICE_FALLBACK_MODEL]*2+[DEFAULT_MODEL])]:
   with self.subTest(values=values),patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(600,500))),patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[(v,'reader') for v in values]) as read:
    self.assertEqual(resolve_invoice_number(self.ocr(),Path('wrong-filename.pdf'),DEFAULT_MODEL,verify_handwriting=True,corroborate=True),number)
    self.assertEqual([c.args[1] for c in read.call_args_list],models)

if __name__=='__main__':unittest.main()
