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


# Public retailer discovery: only explicitly published Product JSON-LD, never inferred sales.
def retailer_products(shop_name, landing, max_items=2):
 try:
  from html.parser import HTMLParser
  class StructuredProducts(HTMLParser):
   def __init__(self):super().__init__();self.active=False;self.parts=[];self.blocks=[]
   def handle_starttag(self,tag,attrs):
    attrs=dict(attrs)
    if tag=='script' and 'ld+json' in attrs.get('type','').lower():self.active=True;self.parts=[]
   def handle_data(self,data):
    if self.active:self.parts.append(data)
   def handle_endtag(self,tag):
    if tag=='script' and self.active:self.blocks.append(''.join(self.parts));self.active=False
  req=urllib.request.Request(landing,headers={'User-Agent':'Mozilla/5.0 (compatible; MarketDashboard/1.0)'})
  with urllib.request.urlopen(req,timeout=12) as r:
   raw=r.read(1200000).decode('utf-8','replace')
   resolved=r.geturl()
  parser=StructuredProducts();parser.feed(raw)
  found=[];seen=set()
  def walk(node):
   if isinstance(node,list):
    for x in node:walk(x)
   elif isinstance(node,dict):
    types=node.get('@type',[])
    if isinstance(types,str):types=[types]
    if 'Product' in types and isinstance(node.get('name'),str):
     name=re.sub(r'\s+',' ',node['name']).strip()[:150]
     link=node.get('url') or resolved
     if isinstance(link,dict):link=link.get('@id','')
     link=urllib.parse.urljoin(resolved,str(link))
     parsed=urllib.parse.urlparse(link)
     if name and parsed.scheme=='https' and parsed.hostname and name.casefold() not in seen:
      seen.add(name.casefold())
      offers=node.get('offers') or {}
      if isinstance(offers,list):offers=offers[0] if offers else {}
      if not isinstance(offers,dict):offers={}
      price=offers.get('price') or offers.get('lowPrice')
      currency=offers.get('priceCurrency','')
      pic=node.get('image') or ''
      if isinstance(pic,list):pic=pic[0] if pic else ''
      if isinstance(pic,dict):pic=pic.get('url','')
      pic=urllib.parse.urljoin(resolved,pic) if isinstance(pic,str) else ''
      found.append({'name':shop_name,'title':name,'url':link,'source':shop_name+' · 官网结构化商品数据','price':str(price) if price is not None else '','currency':str(currency),'image':pic if pic.startswith('https://') else '','summary':'官网公开商品信息；不代表销量或热卖排名。','verified_public_product':True})
    for key,value in node.items():
     if isinstance(value,(dict,list)):walk(value)
  for block in parser.blocks[:30]:
   try:walk(json.loads(block))
   except (ValueError,TypeError):continue
  return found[:max_items]
 except Exception as exc:
  print('Retailer product unavailable:',shop_name,str(exc)[:90]);return []


# Product category monitoring: localized public-news signals, not invented search volumes.
CATEGORY_TERMS={
'DE':{'围巾':'personalisierter Schal','小夜灯':'personalisiertes Nachtlicht','首饰':'personalisierter Schmuck'},
'FR':{'围巾':'écharpe personnalisée','小夜灯':'veilleuse personnalisée','首饰':'bijou personnalisé'},
'ES':{'围巾':'bufanda personalizada','小夜灯':'luz nocturna personalizada','首饰':'joyas personalizadas'},
'IT':{'围巾':'sciarpa personalizzata','小夜灯':'luce notturna personalizzata','首饰':'gioielli personalizzati'},
'NL':{'围巾':'gepersonaliseerde sjaal','小夜灯':'gepersonaliseerd nachtlampje','首饰':'gepersonaliseerde sieraden'},
'NO':{'围巾':'personlig skjerf','小夜灯':'personlig nattlampe','首饰':'personlige smykker'},
'SE':{'围巾':'personlig halsduk','小夜灯':'personlig nattlampa','首饰':'personliga smycken'},
'FI':{'围巾':'personoitu huivi','小夜灯':'personoitu yövalo','首饰':'personoidut korut'},
'PL':{'围巾':'szalik personalizowany','小夜灯':'lampka nocna personalizowana','首饰':'biżuteria personalizowana'}}
def category_signals(code,lang,geo):
 signals=[]
 for category,keyword in CATEGORY_TERMS[code].items():
  q=urllib.parse.quote('"'+keyword+'" when:30d')
  rss=f'https://news.google.com/rss/search?q={q}&hl={lang}&gl={geo}&ceid={geo}:{lang}'
  matches=readfeed(rss,1)
  explore='https://trends.google.com/trends/explore?'+urllib.parse.urlencode({'geo':geo,'date':'today 3-m','q':keyword})
  signals.append({'category':category,'keyword':keyword,'signal_type':'公开新闻匹配' if matches else '关键词观察','news_count_sample':len(matches),'article':matches[0] if matches else None,'url':explore,'source':'Google News RSS / Google Trends 查询入口','note':'有匹配新闻不代表搜索热度上涨；未获取搜索指数。'})
 return signals


# Callie public catalog-derived product families (not a claim about private sales).
CALLIE_FAMILIES={
'首饰':{'DE':'personalisierter Schmuck','FR':'bijoux personnalisés','ES':'joyas personalizadas','IT':'gioielli personalizzati','NL':'gepersonaliseerde sieraden','NO':'personlige smykker','SE':'personliga smycken','FI':'personoidut korut','PL':'biżuteria personalizowana'},
'围巾':{'DE':'personalisierter Schal','FR':'écharpe personnalisée','ES':'bufanda personalizada','IT':'sciarpa personalizzata','NL':'gepersonaliseerde sjaal','NO':'personlig skjerf','SE':'personlig halsduk','FI':'personoitu huivi','PL':'szalik personalizowany'},
'小夜灯':{'DE':'personalisiertes Nachtlicht','FR':'veilleuse personnalisée','ES':'luz nocturna personalizada','IT':'luce notturna personalizzata','NL':'gepersonaliseerd nachtlampje','NO':'personlig nattlampe','SE':'personlig nattlampa','FI':'personoitu yövalo','PL':'lampka nocna personalizowana'},
'毯子':{'DE':'personalisierte Decke','FR':'plaid personnalisé','ES':'manta personalizada','IT':'coperta personalizzata','NL':'gepersonaliseerde deken','NO':'personlig pledd','SE':'personlig filt','FI':'personoitu viltti','PL':'koc personalizowany'},
'包袋':{'DE':'personalisierte Tasche','FR':'sac personnalisé','ES':'bolso personalizado','IT':'borsa personalizzata','NL':'gepersonaliseerde tas','NO':'personlig veske','SE':'personlig väska','FI':'personoitu laukku','PL':'torba personalizowana'},
'照片礼品':{'DE':'Fotogeschenke','FR':'cadeau photo personnalisé','ES':'regalos con fotos','IT':'regali con foto','NL':'fotocadeau','NO':'fotogaver','SE':'fotopresenter','FI':'valokuvalahjat','PL':'prezenty ze zdjęciem'},
'宠物纪念':{'DE':'personalisiertes Haustier Geschenk','FR':'cadeau personnalisé animal','ES':'regalo personalizado mascota','IT':'regalo personalizzato animali','NL':'gepersonaliseerd huisdier cadeau','NO':'personlig kjæledyr gave','SE':'personlig husdjurspresent','FI':'lemmikkilahja omalla kuvalla','PL':'prezent personalizowany dla miłośnika zwierząt'},
'钥匙扣':{'DE':'personalisierter Schlüsselanhänger','FR':'porte clés personnalisé','ES':'llavero personalizado','IT':'portachiavi personalizzato','NL':'gepersonaliseerde sleutelhanger','NO':'personlig nøkkelring','SE':'personlig nyckelring','FI':'personoitu avaimenperä','PL':'brelok personalizowany'},
'水杯':{'DE':'personalisierte Trinkflasche','FR':'gourde personnalisée','ES':'botella personalizada','IT':'borraccia personalizzata','NL':'gepersonaliseerde drinkfles','NO':'personlig drikkeflaske','SE':'personlig vattenflaska','FI':'personoitu juomapullo','PL':'butelka personalizowana'},
'家居装饰':{'DE':'personalisierte Wohndeko','FR':'décoration personnalisée','ES':'decoración personalizada','IT':'decorazioni personalizzate','NL':'gepersonaliseerde woondecoratie','NO':'personlig interiør','SE':'personlig heminredning','FI':'personoitu sisustus','PL':'dekoracje personalizowane'}
}
CALLIE_CATALOG_SOURCE='https://www.callie.com/best-sellers'
def category_signals(code,lang,geo):
 signals=[]
 for category,locales in CALLIE_FAMILIES.items():
  keyword=locales[code]
  explore='https://trends.google.com/trends/explore?'+urllib.parse.urlencode({'geo':geo,'date':'today 3-m','q':keyword})
  signals.append({'category':category,'keyword':keyword,'signal_type':'Callie公开在售品类关键词','url':explore,'source':'Callie官网公开商品 / Google Trends 查询入口','catalog_url':CALLIE_CATALOG_SOURCE,'note':'关键词基于Callie公开商品整理；没有获取搜索指数，不能据此判断热度增长。'})
 return signals

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
 # General country news only: local events across politics, economy, society, culture, weather, etc. Gift industry signals are separate.
 # Headlines are only labeled domestic if sourced from the country-focused search feed.
 local_terms={
  'DE':'Deutschland OR Berlin OR München OR Hamburg OR Bundesregierung',
  'FR':'France OR Paris OR Marseille OR Lyon OR gouvernement',
  'ES':'España OR Madrid OR Barcelona OR Valencia OR Gobierno',
  'IT':'Italia OR Roma OR Milano OR Napoli OR governo',
  'NL':'Nederland OR Amsterdam OR Rotterdam OR Den Haag OR kabinet',
  'NO':'Norge OR Oslo OR Bergen OR Trondheim OR regjeringen',
  'SE':'Sverige OR Stockholm OR Göteborg OR Malmö OR regeringen',
  'FI':'Suomi OR Helsinki OR Tampere OR Turku OR hallitus',
  'PL':'Polska OR Warszawa OR Kraków OR Gdańsk OR rząd'}
 query=urllib.parse.quote('('+local_terms[code]+') when:2d')
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
 products=[]
 for shop_name,landing in SHOPS.get(code,[]):
  discovered=retailer_products(shop_name,landing)
  if discovered:products.extend(discovered)
  else:products.append({'name':shop_name,'title':shop_name+' · 公开商品页面','url':landing,'source':'竞品官网','summary':'该站点未返回可核实的商品结构化数据；点击查看官网。','verified_public_product':False})
 result['countries'][code]={'news':newsitems,'trending':trenditems,'products':products,'ads':[],'gift_keyword':term,'category_signals':category_signals(code,lang,geo),'gift_signals':gift_signals,'gift_signal_method':'Google News 公开搜索匹配，仅作行业线索，不是 Google Trends 指数或销量','news_method':'综合新闻：本国地名与国家关键词优先，国家版新闻补充；不限定礼品行业，搜索匹配不保证事件发生在本国'}
 print(code,'news',len(newsitems),'trends',len(trenditems),'products',sum(bool(p.get('verified_public_product')) for p in products))
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
