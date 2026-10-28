#!/usr/bin/env python3
"""Public RSS data collector. No login, scraping or fabricated scores."""
import os
import json, re, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ROOT=Path(__file__).resolve().parent
COUNTRIES={'DE':('de','DE','personalisierte Geschenke'), 'FR':('fr','FR','cadeau personnalisé'), 'ES':('es','ES','regalos personalizados'), 'IT':('it','IT','regali personalizzati'), 'NL':('nl','NL','gepersonaliseerd cadeau'), 'NO':('no','NO','personlig gave'), 'SE':('sv','SE','personlig present'), 'FI':('fi','FI','personoitu lahja'), 'PL':('pl','PL','prezent personalizowany')}
SHOPS={'DE':[('GRAVURZEILE','https://www.gravurzeile.de/collections/bestseller'),('CARDORI','https://cardori.de/collections/bestseller')], 'FR':[('Cadeaux.com','https://www.cadeaux.com/meilleures-ventes'),('YourSurprise','https://www.yoursurprise.fr/bestsellers')], 'ES':[('Wanapix','https://wanapix.es/'),('Hofmann','https://www.hofmann.es/tienda/regalos')], 'IT':[('Troppotogo','https://www.troppotogo.it/regali-personalizzati')], 'NL':[('YourSurprise','https://www.yoursurprise.nl/bestsellers')], 'NO':[('Walseng Design','https://www.walseng.no/nettbutikk/'),('PersonligGave','https://personliggave.com/')], 'SE':[('Smartphoto','https://www.smartphoto.se/fotopresenter/mugg')], 'FI':[('Puuki','https://www.puuki.fi/pages/personoitu-lahja-isalle'),('GetPersonal','https://www.getpersonal.fi/')], 'PL':[('Crazyshop','https://www.crazyshop.pl/kubki-termiczne%2C15164')]}

ALT_SHOPS={'FR':[('Smartphoto','https://www.smartphoto.fr/')], 'ES':[('YourSurprise','https://www.yoursurprise.es/')], 'NL':[('Smartphoto','https://www.smartphoto.nl/')], 'NO':[('Smartphoto','https://www.smartphoto.no/')], 'SE':[('YourSurprise','https://www.yoursurprise.se/')], 'PL':[('CEWE','https://www.cewe.pl/')]}

# Candidate pages are public product detail pages, not fabricated products.
# Keep a source only after its public metadata yields an actual product image.
PRODUCT_CANDIDATES={
 'FR':[('YourSurprise','https://www.yoursurprise.fr/vases-a-boire/mug-personnalise/mug-couleurs'),('YourSurprise','https://www.yoursurprise.fr/vases-a-boire/mug-personnalise'),('Smartphoto','https://www.smartphoto.fr/cadeaux-photo/mug-personnalise-photo')],
 'ES':[('Wanapix','https://wanapix.es/taza-personalizada-ceramica'),('Wanapix','https://wanapix.es/taza-conica-personalizada'),('Wanapix','https://wanapix.es/taza-personalizada-corazon')],
 'NL':[('Smartphoto','https://www.smartphoto.nl/fotocadeaus/mok-met-foto')],
 'NO':[('Smartphoto','https://www.smartphoto.no/fotogaver/krus')],
 'PL':[('Prazent','https://prazent.pl/products/personalizowany-kubek-z-imieniem-wyjatkowy-prezent'),('Tortli','https://tortli.pl/products/kubek-dla-par-24'),('KubkiBezCenzury','https://kubkibezcenzury.pl/kubki-z-wlasnym-napisem/585-kubek-z-twoim-napisem.html'),('CEWE','https://www.cewe.pl/fotoprezenty/kubek-ceramiczny-ze-zdjeciem.html'),('CEWE','https://www.cewe.pl/fotoprezenty/kubek-z-inicjalami-i-zdjeciem.html'),('CEWE','https://www.cewe.pl/fotoprezenty/kubek-magiczny-ze-zdjeciem.html')],
}
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



# Second-stage product discovery: inspect product links on public collection pages.
# Only show a card when the linked detail page publishes Product JSON-LD.
def discover_product_links(landing, max_links=3):
 try:
  from html.parser import HTMLParser
  class Links(HTMLParser):
   def __init__(self):super().__init__();self.links=[]
   def handle_starttag(self,tag,attrs):
    if tag!='a':return
    a=dict(attrs);href=a.get('href','')
    if href:self.links.append(href)
  req=urllib.request.Request(landing,headers={'User-Agent':'Mozilla/5.0 (compatible; MarketDashboard/1.0)'})
  with urllib.request.urlopen(req,timeout=12) as response:
   raw=response.read(1600000).decode('utf-8','replace');base=response.geturl()
  root=urllib.parse.urlparse(base)
  parser=Links();parser.feed(raw)
  found=[];seen=set()
  for href in parser.links:
   url=urllib.parse.urljoin(base,href)
   u=urllib.parse.urlparse(url)
   if u.scheme!='https' or u.hostname!=root.hostname:continue
   path=u.path.lower()
   if not any(t in path for t in ('/products/','/product/','/produkt/','/produit/','/producto/','/prodotti/','/p/','/artikel/','/prod_','/cadeaux-photo/')):continue
   if any(t in path for t in ('/collections/','/category/','/categories/')):continue
   clean=urllib.parse.urlunparse((u.scheme,u.netloc,u.path,'','',''))
   if clean in seen:continue
   seen.add(clean);found.append(clean)
   if len(found)>=max_links:break
  return found
 except Exception as exc:
  print('Product links unavailable:',landing,str(exc)[:110]);return []

def retailer_product_detail(shop_name,landing,max_items=2):
 links=discover_product_links(landing,3)
 products=[];seen=set()
 for link in links:
  for entry in retailer_products(shop_name,link,2):
   # The detail page must actually identify a product, not merely the parent store.
   if not entry.get('verified_public_product') or not entry.get('image'):continue
   url=entry.get('url','')
   if urllib.parse.urlparse(url).hostname!=urllib.parse.urlparse(landing).hostname:continue
   if url in seen:continue
   seen.add(url);products.append(entry)
   if len(products)>=max_items:return products
 return products


# Read-only public Shopify storefront catalog, where enabled by the retailer.
# No API keys, private admin endpoints, or inferred bestseller rankings.
def storefront_products(shop_name, landing, max_items=2):
 try:
  root=urllib.parse.urlparse(landing)
  endpoint=f'{root.scheme}://{root.netloc}/products.json?limit=12'
  req=urllib.request.Request(endpoint,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
  with urllib.request.urlopen(req,timeout=9) as response:
   if 'json' not in response.headers.get('Content-Type','').lower():return []
   data=json.loads(response.read(600000))
  items=data.get('products',[]) if isinstance(data,dict) else []
  out=[]
  for product in items:
   if not isinstance(product,dict):continue
   title=str(product.get('title') or '').strip()
   handle=str(product.get('handle') or '').strip()
   image=product.get('image') or {}
   images=product.get('images') or []
   pic=(image.get('src') if isinstance(image,dict) else '') or ((images[0].get('src') or '') if images and isinstance(images[0],dict) else '')
   variants=product.get('variants') or []
   variant=variants[0] if variants and isinstance(variants[0],dict) else {}
   price=variant.get('price','')
   if not (title and handle and isinstance(pic,str) and pic.startswith('https://')):continue
   url=f'{root.scheme}://{root.netloc}/products/'+urllib.parse.quote(handle,safe='-')
   out.append({'name':shop_name,'title':title[:150],'url':url,'source':shop_name+' · 官网公开商品目录','price':str(price) if price is not None else '','currency':'','image':pic,'summary':'公开商品目录展示；不代表热卖或销量。价格币种需以官网为准。','verified_public_product':True})
   if len(out)>=max_items:break
  return out
 except Exception as exc:
  print('Public storefront catalog unavailable:',shop_name,str(exc)[:100]);return []

# Additional public product pages discovered from the retailer's sitemap.
def sitemap_product_links(landing,max_links=3):
 try:
  u=urllib.parse.urlparse(landing);root=f'{u.scheme}://{u.netloc}'
  req=urllib.request.Request(root+'/sitemap.xml',headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=9) as r:raw=r.read(450000)
  xml=ET.fromstring(raw)
  urls=[(x.text or '').strip() for x in xml.iter() if x.tag.rsplit('}',1)[-1]=='loc']
  sitemap=next((x for x in urls if 'sitemap_products' in x),None)
  if sitemap:
   with urllib.request.urlopen(urllib.request.Request(sitemap,headers={'User-Agent':'Mozilla/5.0'}),timeout=9) as r:raw=r.read(650000)
   xml=ET.fromstring(raw)
   urls=[(x.text or '').strip() for x in xml.iter() if x.tag.rsplit('}',1)[-1]=='loc']
  result=[]
  for link in urls:
   parsed=urllib.parse.urlparse(link)
   if parsed.hostname!=u.hostname or parsed.scheme!='https':continue
   if any(t in parsed.path.lower() for t in ('/products/','/product/','/produkt/','/produit/','/producto/','/prodotti/','/prod_')):
    result.append(link)
   if len(result)>=max_links:break
  return result
 except Exception as exc:
  print('Sitemap discovery unavailable:',landing,str(exc)[:90]);return []

def discover_retailer_cards(shop_name,landing,max_items=2):
 direct=retailer_products(shop_name,landing,max_items)
 if not any(x.get('image') for x in direct):direct=html_product_metadata(shop_name,landing)
 if len([x for x in direct if x.get('image')])>=max_items:return direct[:max_items]
 links=discover_product_links(landing,10)
 if len(links)<5:links+=sitemap_product_links(landing,8)
 verified=[x for x in direct if x.get('image')];seen={x.get('url') for x in verified}
 for link in dict.fromkeys(links[:12]):
  if len(verified)>=max_items:break
  candidates=retailer_products(shop_name,link,1)
  if not any(x.get('image') for x in candidates):
   candidates=html_product_metadata(shop_name,link)
  for item in candidates:
   if item.get('image') and item.get('url') not in seen:
    verified.append(item);seen.add(item.get('url'))
 if len(verified)<max_items:
  for item in storefront_products(shop_name,landing,max_items):
   if item.get('url') not in seen:
    verified.append(item);seen.add(item.get('url'))
   if len(verified)>=max_items:break
 return verified[:max_items] or direct[:max_items]


# Public HTML product metadata fallback for stores without JSON-LD.
def html_product_metadata(shop_name,url):
 try:
  from html.parser import HTMLParser
  class Metadata(HTMLParser):
   def __init__(self):super().__init__();self.meta={};self.title='';self.in_title=False
   def handle_starttag(self,tag,attrs):
    a=dict(attrs)
    if tag=='meta':
     key=(a.get('property') or a.get('name') or '').lower()
     if key:self.meta[key]=a.get('content','')
    if tag=='title':self.in_title=True
   def handle_data(self,data):
    if self.in_title:self.title+=data
   def handle_endtag(self,tag):
    if tag=='title':self.in_title=False
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
  with urllib.request.urlopen(req,timeout=9) as r:
   final=r.geturl();html=r.read(900000).decode('utf-8','replace')
  parser=Metadata();parser.feed(html);m=parser.meta
  kind=(m.get('og:type') or '').lower()
  name=(m.get('og:title') or m.get('twitter:title') or '').strip()
  image=(m.get('og:image:secure_url') or m.get('og:image') or m.get('twitter:image') or '').strip()
  image=urllib.parse.urljoin(final,image)
  price=(m.get('product:price:amount') or m.get('og:price:amount') or m.get('product:sale_price:amount') or '').strip()
  currency=(m.get('product:price:currency') or m.get('og:price:currency') or '').strip()
  path=urllib.parse.urlparse(final).path.lower()
  product_path=any(t in path for t in ('/products/','/product/','/produkt/','/produit/','/producto/','/prodotti/','/artikel/'))
  if not (name and image.startswith('https://') and (kind=='product' or product_path)):return []
  return [{'name':shop_name,'title':name[:150],'url':final,'source':shop_name+' · 官网商品页公开元数据','price':price,'currency':currency,'image':image,'summary':'官网商品页公开信息；不代表热卖排名。','verified_public_product':True}]
 except Exception as exc:
  print('Product metadata unavailable:',url,str(exc)[:90]);return []


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
  signals.append({'category':category,'keyword':keyword,'signal_type':'Callie商品方向候选关键词','url':explore,'source':'Callie商品方向关键词池 / Google Trends 查询入口','catalog_url':CALLIE_CATALOG_SOURCE,'note':'关键词是Callie商品方向候选，具体在售SKU尚未逐项核实；此处没有搜索指数。'})
 return signals

def fetch_meta_ads(brand,country):
 token=os.environ.get('META_AD_LIBRARY_ACCESS_TOKEN','').strip()
 if not token:return []
 params={'access_token':token,'ad_reached_countries':json.dumps([country]),'search_terms':brand,'ad_type':'ALL','ad_active_status':'ALL','limit':3,'fields':'id,page_name,ad_delivery_start_time,ad_snapshot_url,ad_creative_bodies,ad_creative_link_titles'}
 try:
  req=urllib.request.Request('https://graph.facebook.com/v22.0/ads_archive?'+urllib.parse.urlencode(params),headers={'User-Agent':'MarketResearch/1.0'})
  with urllib.request.urlopen(req,timeout=12) as resp:payload=json.load(resp)
  return [{'id':str(x.get('id','')),'title':x.get('page_name',brand),'brand':brand,'url':x['ad_snapshot_url'],'source':'Meta Ad Library','description':(x.get('ad_creative_bodies') or [''])[0],'started_at':x.get('ad_delivery_start_time',''),'record_type':'verified_ad','media_status':'官方快照可查看素材，媒体文件未直接获取'} for x in payload.get('data',[]) if str(x.get('ad_snapshot_url','')).startswith('https://')]
 except Exception as exc:
  print('Meta API unavailable:',country,brand,str(exc)[:140]);return []

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
result={'updated_at':datetime.now(timezone.utc).isoformat(),'countries':{},'quality':{'country_count':len(COUNTRIES),'product_coverage':{},'ad_coverage':{},'missing_product_countries':[]}}
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
 source_audit=[]
 selected=[]
 candidates=PRODUCT_CANDIDATES.get(code,[])+SHOPS.get(code,[])+ALT_SHOPS.get(code,[])
 for shop_name,landing in candidates:
  if len(products)>=6:break
  discovered=discover_retailer_cards(shop_name,landing,3)
  verified=[x for x in discovered if x.get('verified_public_product') and x.get('image') and x.get('url')]
  source_audit.append({'brand':shop_name,'url':landing,'verified_count':len(verified)})
  if not verified:continue
  selected.append((shop_name,landing))
  for item in verified:
   if any(x.get('url')==item.get('url') for x in products):continue
   item['selection_basis']='官网热销/推荐栏目' if any(k in landing.lower() for k in ('bestseller','meilleures-ventes')) else '官网公开商品（未验证热销排名）'
   products.append(item)
 # Meta Ad Library discovery links are verified navigation, not individual ads.
 # Real ad records require Meta-approved API access or separately verified public post URLs.
 ad_searches=[]
 for brand,landing in selected:
  query=urllib.parse.urlencode({'active_status':'all','ad_type':'all','country':geo,'q':brand,'search_type':'keyword_unordered'})
  ad_searches.append({'brand':brand,'country':code,'url':'https://www.facebook.com/ads/library/?'+query,'source':'Meta Ad Library','record_type':'search_link','status':'广告资料库实时检索（非单条已核实广告）','category':'竞品品牌'})
 for category in ('首饰','围巾','照片礼品'):
  keyword=CALLIE_FAMILIES.get(category,{}).get(code)
  if not keyword:continue
  query=urllib.parse.urlencode({'active_status':'all','ad_type':'all','country':geo,'q':keyword,'search_type':'keyword_unordered'})
  ad_searches.append({'brand':category,'keyword':keyword,'country':code,'url':'https://www.facebook.com/ads/library/?'+query,'source':'Meta Ad Library','record_type':'search_link','status':'按Callie品类检索公开广告','category':'Callie同类商品'})
 real_ads=[]
 if os.environ.get('META_AD_LIBRARY_ACCESS_TOKEN'):
  for brand,_ in selected[:2]:real_ads.extend(fetch_meta_ads(brand,geo))
 result['countries'][code]={'news':newsitems,'trending':trenditems,'products':products,'product_source_audit':source_audit,'ads':real_ads,'ad_searches':ad_searches,'ad_data_status':('已获取官方广告记录' if real_ads else '暂无可核实广告记录；官方接口需要授权'),'gift_keyword':term,'category_signals':category_signals(code,lang,geo),'gift_signals':gift_signals,'gift_signal_method':'Google News 公开搜索匹配，仅作行业线索，不是 Google Trends 指数或销量','news_method':'综合新闻：本国地名与国家关键词优先，国家版新闻补充；不限定礼品行业，搜索匹配不保证事件发生在本国'}
 verified_count=sum(bool(p.get('verified_public_product') and p.get('image')) for p in products)
 result['quality']['product_coverage'][code]=verified_count
 result['quality']['ad_coverage'][code]=len(real_ads)
 if not verified_count:result['quality']['missing_product_countries'].append(code)
 print(code,'news',len(newsitems),'trends',len(trenditems),'verified_products',verified_count,'ad_records',len(real_ads))
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
