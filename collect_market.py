#!/usr/bin/env python3
"""Public RSS data collector. No login, scraping or fabricated scores."""
import json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
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

previous={}
path=ROOT/'data/market.json'
if path.exists():
 try:previous=json.loads(path.read_text(encoding='utf-8')).get('countries',{})
 except Exception:pass
result={'updated_at':datetime.now(timezone.utc).isoformat(),'countries':{}}
for code,(lang,geo,term) in COUNTRIES.items():
 query=urllib.parse.quote('("'+term+'" OR "'+term.split()[0]+'")')
 news=f'https://news.google.com/rss/search?q={query}&hl={lang}&gl={geo}&ceid={geo}:{lang}'
 trending=f'https://trends.google.com/trending/rss?geo={geo}'
 newsitems=readfeed(news,3)
 trenditems=readfeed(trending,3)
 old=previous.get(code,{})
 # Do not carry old items forward silently; the dashboard should distinguish unavailable from fresh.
 products=[{'name':n,'title':n+' · 公开商品/热卖页面','url':u,'source':'竞品官网','summary':'已确认候选来源；商品排名、价格和销量尚未自动验证。'} for n,u in SHOPS.get(code,[])]
 result['countries'][code]={'news':newsitems,'trending':trenditems,'products':products,'ads':[]}
 print(code,'news',len(newsitems),'trends',len(trenditems))
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
