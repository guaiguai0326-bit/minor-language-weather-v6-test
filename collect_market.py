#!/usr/bin/env python3
"""Public RSS data collector. No login, scraping or fabricated scores."""
import json, re, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ROOT=Path(__file__).resolve().parent
COUNTRIES={'DE':('de','DE','personalisierte Geschenke'), 'FR':('fr','FR','cadeau personnalisé'), 'ES':('es','ES','regalos personalizados'), 'IT':('it','IT','regali personalizzati'), 'NL':('nl','NL','gepersonaliseerd cadeau'), 'NO':('no','NO','personlig gave'), 'SE':('sv','SE','personlig present'), 'FI':('fi','FI','personoitu lahja'), 'PL':('pl','PL','prezent personalizowany')}
SHOPS={'DE':[('GRAVURZEILE','https://www.gravurzeile.de/collections/bestseller'),('CARDORI','https://cardori.de/collections/bestseller')], 'FR':[('Cadeaux.com','https://www.cadeaux.com/meilleures-ventes'),('YourSurprise','https://www.yoursurprise.fr/bestsellers')], 'ES':[('Wanapix','https://wanapix.es/'),('Hofmann','https://www.hofmann.es/tienda/regalos')], 'IT':[('Troppotogo','https://www.troppotogo.it/regali-personalizzati')], 'NL':[('YourSurprise','https://www.yoursurprise.nl/bestsellers')], 'NO':[('Walseng Design','https://www.walseng.no/nettbutikk/'),('PersonligGave','https://personliggave.com/')], 'SE':[('Smartphoto','https://www.smartphoto.se/fotopresenter')], 'FI':[('Puuki','https://www.puuki.fi/pages/personoitu-lahja-isalle'),('GetPersonal','https://www.getpersonal.fi/')], 'PL':[('Crazyshop','https://www.crazyshop.pl/')]}

def readfeed(url,limit=3):
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; MarketDashboard/1.0)'})
  with urllib.request.urlopen(req,timeout=17) as response: raw=response.read(1300000)
  root=ET.fromstring(raw)
  entries=[]
  for item in root.findall('.//item')[:limit]:
   def get(k):return (item.findtext(k) or '').strip()
   title=re.sub(r'<[^>]+>','',get('title'))[:220]
   link=get('link')
   if not title or not link.startswith('https://'):continue
   dt=get('pubDate');iso=''
   if dt:
    try:iso=parsedate_to_datetime(dt).astimezone(timezone.utc).isoformat()
    except Exception:pass
   source=item.findtext('source') or urllib.parse.urlparse(link).hostname or 'RSS'
   entries.append({'title':title,'url':link,'source':source,'published':iso})
  return entries
 except Exception as e:
  print('Feed unavailable:',url,str(e)[:130]);return []

# Public Google Translate endpoint: best-effort, unofficial, may be rate-limited or change.
# Do not claim translation success if the service fails. Cached results reduce requests.
def translate_zh(text,lang,cache):
 if not text:return ''
 key=lang+'|'+text
 if key in cache:return cache[key]
 try:
  query=urllib.parse.urlencode({'client':'gtx','sl':lang,'tl':'zh-CN','dt':'t','q':text})
  req=urllib.request.Request('https://translate.googleapis.com/translate_a/single?'+query,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=10) as r:data=json.loads(r.read(200000).decode('utf-8'))
  result=''.join(str(x[0] or '') for x in data[0] if isinstance(x,list))
  if result and result.strip().casefold()!=text.strip().casefold():
   cache[key]=result.strip();return cache[key]
 except Exception as exc:print('Translation unavailable:',lang,str(exc)[:100])
 return ''

previous={}
path=ROOT/'data/market.json'
if path.exists():
 try:previous=json.loads(path.read_text(encoding='utf-8')).get('countries',{})
 except Exception:pass
cache={}
for country_code,old_items in previous.items():
 lang=COUNTRIES.get(country_code,('auto',))[0]
 for group in ('news','trending'):
  for entry in old_items.get(group,[]):
   if entry.get('title') and entry.get('title_zh'):cache[lang+'|'+entry['title']]=entry['title_zh']
result={'updated_at':datetime.now(timezone.utc).isoformat(),'countries':{}}
for code,(lang,geo,term) in COUNTRIES.items():
 # Country-first news: search local domestic headlines; supplement with local edition top stories.
 # Headlines are only labeled domestic if sourced from the country-focused search feed.
 local_terms={
  'DE':'Deutschland OR Bundesregierung OR Bundestag',
  'FR':'France OR gouvernement français OR Assemblée nationale',
  'ES':'España OR Gobierno español OR Congreso',
  'IT':'Italia OR governo italiano OR Parlamento',
  'NL':'Nederland OR kabinet OR Tweede Kamer',
  'NO':'Norge OR regjeringen OR Stortinget',
  'SE':'Sverige OR regeringen OR riksdagen',
  'FI':'Suomi OR hallitus OR eduskunta',
  'PL':'Polska OR rząd OR Sejm'}
 query=urllib.parse.quote('('+local_terms[code]+') when:3d')
 domestic_url=f'https://news.google.com/rss/search?q={query}&hl={lang}&gl={geo}&ceid={geo}:{lang}'
 edition_url=f'https://news.google.com/rss?hl={lang}&gl={geo}&ceid={geo}:{lang}'
 trending=f'https://trends.google.com/trending/rss?geo={geo}'
 domestic=readfeed(domestic_url,5)
 for x in domestic:x['scope']='本国热点候选'
 general=readfeed(edition_url,5)
 for x in general:x['scope']='当地媒体关注'
 newsitems=[];seen=set()
 for entry in domestic+general:
  token=re.sub(r'\W+','',entry['title'].lower())[:90]
  if token in seen:continue
  seen.add(token);newsitems.append(entry)
  if len(newsitems)>=3:break
 trenditems=readfeed(trending,3)
 for x in trenditems:x['scope']='当地综合热搜（非礼品需求）' 
 old=previous.get(code,{})
 for group in (newsitems,trenditems):
  for entry in group:
   entry['title_zh']=translate_zh(entry['title'],lang,cache)
   entry['translation_status']='translated' if entry['title_zh'] else 'unavailable'
   time.sleep(0.12)
 # Industry-related public news signals: search evidence, NOT Google Trends volume.
 gift_query=urllib.parse.quote('"'+term+'" when:14d')
 gift_feed=f'https://news.google.com/rss/search?q={gift_query}&hl={lang}&gl={geo}&ceid={geo}:{lang}'
 gift_signals=readfeed(gift_feed,3)
 for entry in gift_signals:
  entry['scope']='礼品行业相关新闻（搜索匹配，非销量或搜索指数）'
  entry['title_zh']=translate_zh(entry['title'],lang,cache)
  entry['translation_status']='translated' if entry['title_zh'] else 'unavailable'
  time.sleep(0.12)
 # Do not carry old items forward silently; the dashboard should distinguish unavailable from fresh.
 products=[{'name':n,'title':n+' · 公开商品/热卖页面','url':u,'source':'竞品官网','summary':'已确认候选来源；商品排名、价格和销量尚未自动验证。'} for n,u in SHOPS.get(code,[])]
 result['countries'][code]={'news':newsitems,'trending':trenditems,'products':products,'ads':[],'gift_keyword':term,'gift_signals':gift_signals,'gift_signal_method':'Google News 公开搜索匹配，仅作行业线索，不是 Google Trends 指数或销量','news_method':'本国关键词优先，国家版头条补充；搜索匹配不等于事件必然发生在本国'}
 print(code,'news',len(newsitems),'trends',len(trenditems))
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
