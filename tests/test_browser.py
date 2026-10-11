from pathlib import Path
import sys,tempfile,logging,json,http.server,threading
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src import scraper
from src.db import open_db
from src.config import Region,Config,Delays,BrowserConfig,OutputConfig
from playwright.sync_api import TimeoutError as PWTimeout

listing='''<html><body><h1 data-marker="item-view/title-info">Sample roof installation</h1><a data-marker="seller-link/link" href="/user/abcdef">Sample Company</a><span data-marker="item-view/item-address">Test City</span></body></html>'''
profile='''<html><head><title>Sample Company - официальная страница во всех регионах</title></head><body><h1 data-marker="page-title/text">Sample Company</h1><div data-marker="seller-info/address">Test City</div><div data-marker="seller-info/description">Contact contact@example.com</div></body></html>'''
search='''<article data-marker="item"><a data-marker="item-title" href="/sample/predlozheniya_uslug/roof_123">Sample listing</a></article>'''
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  content=profile if self.path.startswith('/user/') else listing if self.path.startswith('/sample/') else search
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(content.encode())
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
scraper.BASE_URL=f'http://127.0.0.1:{server.server_port}'
result={}
try:
 with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
  browser=p.chromium.launch(channel='chrome',headless=True)
  context=browser.new_context()
  page=context.new_page();page.goto(scraper.BASE_URL)
  links=scraper.collect_listing_links(page,logging.getLogger('test'))
  assert links==[scraper.BASE_URL+'/sample/predlozheniya_uslug/roof_123']
  result['search_links']='pass'
  with open_db(Path(temp)/'state.db') as db:
   stats=scraper.ScrapeStats()
   assert scraper.scrape_listing_and_profile(context,links[0],'roof',Region('sample','Test City'),db,logging.getLogger('test'),stats)
   record=db.all_profiles()[0]
   assert record['name']=='Sample Company' and record['email']=='contact@example.com'
   assert db.count_profiles()==1
   assert scraper.scrape_listing_and_profile(context,links[0],'roof',Region('sample','Test City'),db,logging.getLogger('test'),stats)
   assert db.count_profiles()==1
   result['listing_profile_contact_and_duplicate']='pass'
  profile='<html><body><h1>Доступ ограничен</h1></body></html>'
  scraper.pause_for_manual_captcha=lambda *_:None
  with open_db(Path(temp)/'blocked.db') as db:
   saved=scraper.scrape_listing_and_profile(context,links[0],'roof',Region('sample','Test City'),db,logging.getLogger('test'),scraper.ScrapeStats())
   result['blocked_profile_saved_as_success']=saved and db.count_profiles()==1
   assert not saved and db.count_profiles()==0
  class FailedPage:
   def goto(self,*args,**kwargs):raise PWTimeout('Synthetic search timeout')
   def close(self):pass
  class FailedContext:
   def new_page(self):return FailedPage()
  cfg=Config(['roof'],[Region('sample','Test City')],Delays(0,0,0,0,0,0),1,BrowserConfig(),None,OutputConfig(),'state.db')
  with open_db(Path(temp)/'timeout.db') as db:
   scraper.run_scrape(FailedContext(),cfg,db,logging.getLogger('test'))
   result['timed_out_query_marked_complete']=db.query_region_done('roof','sample')
   assert not result['timed_out_query_marked_complete']
  profile='<html><body><h1>Sample Company</h1></body></html>'
  cfg.regions=[Region('search','Test City')]
  with open_db(Path(temp)/'complete.db') as db:
   db.log_run_stats('roof','search',0)
   assert not db.query_region_done('roof','search')
   first=scraper.run_scrape(context,cfg,db,logging.getLogger('test'))
   assert first.profiles_new==1 and db.query_region_done('roof','search')
   second=scraper.run_scrape(context,cfg,db,logging.getLogger('test'))
   assert second.profiles_new==0 and db.count_profiles()==1
   result['full_pipeline_and_completed_restart']='pass'
   result['legacy_run_stats_not_completion']='pass'
  page.goto(scraper.BASE_URL+'/user/abcdef')
  assert not scraper.looks_like_captcha_or_block(page)
  page.set_content('<body>Подтвердите, что вы не робот</body>')
  assert scraper.looks_like_captcha_or_block(page)
  result['block_detection']='pass'
  page.screenshot(path=str(Path(tempfile.gettempdir())/'avito-public-block.png'))
  browser.close()
 print(json.dumps(result))
 (Path(tempfile.gettempdir())/'avito-public-browser-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
finally:server.shutdown();server.server_close()
