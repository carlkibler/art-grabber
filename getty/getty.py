# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import sys
import logging
import time
from collections import defaultdict
import os, errno


# todo move this out of here
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
fh = logging.FileHandler('getty.log')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
log.addHandler(fh)
log.addHandler(ch)


GETTY_SEARCH_URL =  "http://search.getty.edu/gateway/search?q=&cat=type&types=%22Paintings%22&highlights=%22Open%20Content%20Images%22&rows=5&srt=a&dir=s&dsp=0&img=0&pg=1"
GETTY_IMAGE_URL = "http://d2hiq5kf5j4p5h.cloudfront.net/{0:0>6}01.jpg"
GETTY_THUMBNAIL_URL = "http://www.getty.edu/art/collections/images/thumb/{0:0>6}01-T.JPG"
"{0:0>6}".format(1)

# HTML libs make the simple case of "give me everything" painful
def collect_values(values):
    new_values = []
    for value in values:
        if len(value.contents[1]) > 1:
            new_values.append(value.contents[1].contents)
        else:
            new_values.append(value.contents[1].contents[0])
    return new_values

def clean_topics(value):
    tags = []
    if isinstance(value, basestring):
        return value.split('/')
    for v in value:
        if isinstance(v, basestring):
            tags.extend(v.split('/'))
        else:
            for tag in [text for text in v.stripped_strings]:
                tags.extend(clean_topics(tag))
    return [tag.strip() for tag in tags]

def clean_text(value):
    pieces = []
    if isinstance(value, basestring):
        return value
    for v in value:
        if isinstance(v, basestring):
            pieces.append(v)
        else:
            for piece in [text for text in v.stripped_strings]:
                pieces.append(clean_text(piece))
    return [piece.strip() for piece in pieces]

def process_asset(raw_asset):
    keys = raw_asset.find_all('td', class_='cs-label')
    values = raw_asset.find_all('td', class_='cs-value')
    assert len(keys) == len(values)

    # clean up keys
    keys = [key.text.replace('<p>', '').replace('</p>', '').strip().strip(':') for key in keys]
    values = collect_values(values)
    data = defaultdict(unicode)
    data.update(zip(keys, values))

    try:
        data['Topic'] = clean_topics(data['Topic'])
        data[u'Source URL'] = data['Primary Title']['href']
        data[u'Primary Title'] = data['Primary Title'].text
        data['Object Name'] = clean_text(data['Object Name'])
        if u'Alternate Number' in data:
            data['Alternate Number'] = clean_text(data['Alternate Number'])
        data['Dimensions'] = data['Dimensions'].split('\n')
        data[u'Object ID'] = data['Source URL'].split('objectid=')[-1]
        data[u'Image URL'] = GETTY_IMAGE_URL.format(data['Object ID'])
        data[u'Thumbnail URL'] = GETTY_THUMBNAIL_URL.format(data['Object ID'])
    except Exception as e:
        print 'Parsing exception: ', e
        log.debug(e)
        import debug

    return data

def process(index_page):

    # parse
    soup = BeautifulSoup(index_page)

    # find asset sections
    # <div class="cs-result-data-full" style="display: none;">
    sections = soup.find_all('div', class_='cs-result-data-full')

    assets = []
    for raw_asset in sections:
        data = process_asset(raw_asset)
        assets.append(data)
    return assets

def url_ok(url):
    resp = requests.head(url)
    return resp.status_code == 200

def test_assets(assets):
    for asset in assets:
        print "{} -> {} {}".format(
            asset['Object ID'],
            url_ok(asset['Image URL']),
            url_ok(asset['Thumbnail URL'])
        )

def download_from_url(filename, url):
    log.debug("Download to {} from {}".format(filename, url))
    start = time.time()
    try:
        data = requests.get(url, stream=True)
        if data.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in data.iter_content(1024):
                    f.write(chunk)
    except:
        log.warning("Download failure. url={}".format(url))
    elapsed = time.time() - start
    log.debug("Completed download to {} in {} seconds".format(filename, elapsed))
    return True, elapsed


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise


def download_asset(asset, skip_existing=True):
    log.info("Download asset {}".format(asset['Object ID']))
    mkdir_p("assets/getty/image/")
    mkdir_p("assets/getty/thumb/")

    image_path = "assets/getty/image/{}.jpg".format(asset['Object ID'])
    thumb_path = "assets/getty/thumb/{}.jpg".format(asset['Object ID'])
    if not os.path.exists(image_path):
        outcome, elapsed = download_from_url(image_path, asset['Image URL'])
    if not os.path.exists(thumb_path):
        outcome, elapsed = download_from_url(thumb_path, asset['Thumbnail URL'])


def bulk_download(assets, delay=1.0):
    import debug
    log.info("Downloading {} assets".format(len(assets)))
    start = time.time()
    for asset in assets:
        download_asset(asset)
        time.sleep(delay)
        elapsed = time.time()
        log.info("Bulk download elapsed time {} seconds".format(elapsed))


if __name__=='__main__':
    if 'live' in sys.argv:
        log.info("Processing live data from {}".format(GETTY_SEARCH_URL))
        index_page = requests.get(GETTY_SEARCH_URL).text
    else:
        index_page = open('getty_index.html', 'rb').read()
    assets = process(index_page)
    log.info("Processed {} assets".format(len(assets)))
    log.info("Testing assets")
    # test_assets(assets)
    bulk_download(assets)
