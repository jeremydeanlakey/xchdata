import httplib, ssl, urllib, urllib2, socket, cookielib, re, datetime, os

import credentials, queries

    
class HTTPSConnectionV3(httplib.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        httplib.HTTPSConnection.__init__(self, *args, **kwargs)
    
    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        try:
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, ssl_version=ssl.PROTOCOL_SSLv3)
        except ssl.SSLError, e:
            print("Trying SSLv3.")
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, ssl_version=ssl.PROTOCOL_SSLv23)

class HTTPSHandlerV3(urllib2.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(HTTPSConnectionV3, req)

def login():
    cj = cookielib.CookieJar()
    urllib2.install_opener(urllib2.build_opener(urllib2.HTTPCookieProcessor(cj),HTTPSHandlerV3()))
    url0 = 'https://courtapps.utcourts.gov/XchangeWEB/'
    page0 = urllib2.urlopen(url0).read()
    data = {'submit':'Login'}
    data['username'] = credentials.username
    data['password'] = credentials.password
    encoded = urllib.urlencode(data)
    url1 = 'https://courtapps.utcourts.gov/XchangeWEB/login'
    reqlogin = urllib2.Request(url = url1, data=encoded)
    page1 = urllib2.urlopen(reqlogin).read()

def fetch_qry(params, page=1):
    usearch = 'https://courtapps.utcourts.gov/XchangeWEB/CaseSearchServlet?_=gyRWOWiixsKPNwj%2Bv8UH3lE0xAQrpFdW'
    #qry = EMPTY_QUERY.copy()
    #qry.update(params)
    params['currentPage'] = page
    encoded = urllib.urlencode(params)
    reqsearch = urllib2.Request(url = usearch, data=encoded)
    pgsearch = urllib2.urlopen(reqsearch).read()
    return pgsearch

def remove_tags(html):
    return re.sub('<[^>]*>', '', html)

def extract_link(html):
    link = re.findall("openPopup\('([^']*)'", html)
    if not link:
        return None
    return urllib2.urlparse.urljoin('https://courtapps.utcourts.gov/XchangeWEB/', link[0])

def extract_caserows(html):
    html = html.replace('&nbsp;', '')
    relevant = re.findall(r'History / .*</BODY>', html, re.DOTALL)[0]
    start = r'<TR class="bottomborder" style="font-size:8pt;">[\s]*'
    item = r'<[Tt][dD][^>]*>(.*?)</[tT][dD]>[\s]*'
    finish = r'</TR>'
    pattern = start + item * 10 + finish
    matches = re.findall(pattern, relevant, re.IGNORECASE)
    cases = []
    for m in matches:
        p = {
            'County': m[0],
            'CourtLocation': m[1],
            'CaseType': m[2],
            'CaseNumber': remove_tags(m[3]),
            'FilingDate': m[4],
            'PartiesLink': extract_link(m[6]),
            #'FirstName': remove_tags(m[5]),
            #'LastName': remove_tags(m[6]),
            #'BirthDate': m[7],
            #'PartyCode': m[8],
            'CaseHistoryLink': extract_link(m[9]),
            }
        cases.append(p)
    return cases

def extract_parties(html):
    start = r'<tr style="font-size:8pt;">[\s]*'
    item = r'<TD style="font-size:8pt;">([^<]*)</TD>[\s]*'
    finish = r'</TR>'
    pattern = start + item * 10 + finish
    matches = re.findall(pattern, html)
    parties = []
    for m in matches:
        p = {
            #'CaseNumber': m[0],
            #'CaseType': m[1],
            'PartyName': m[2],
            'PartyType': m[3],
            #'BirthDate': m[4],
            'Address': m[5],
            'Address2': m[6],
            'City': m[7],
            'State': m[8],
            'ZipCode': m[9],
            }
        parties.append(p)
    return parties

def combine_parties(parties):
    addresses = {}
    for p in parties:
        if not p['Address']:
            continue
        if not p['State']:
            p['State'] = 'UT'
        k = p['PartyType'] + p['Address'] + p['Address2'] + p['ZipCode']
        a = addresses.get(k)
        if not a:
            a = p.copy()
            # Turn the Party into a list of parties
            a['PartyName'] = [a['PartyName']]
        else:
            a['PartyName'].append(p['PartyName'])
        addresses[k] = a
    return addresses.values()

def fetch_casehistory(link):
    return urllib2.urlopen(link).read()

def run_query(qry, mindate='', maxrows=500, prior_cases=[]):
    params = qry['params']
    if len(mindate) > 10:
        mindate = mindate[:10]
    if params['sortBy'] == 'Judgment Date':
        mindateMMDDYYYY = ''
        if mindate:
            mindateMMDDYYYY = '%s-%s-%s' % (mindate[5:7], mindate[8:10], mindate[:4])
        params['OldJudgmentStartDate'] = mindateMMDDYYYY
        params['OldJudgmentEndDate'] = datetime.datetime.today().strftime('%m-%d-%Y')
        params['judgmentStartDate'] = mindateMMDDYYYY
        params['judgmentEndDate'] = datetime.datetime.today().strftime('%m-%d-%Y')
    else:
        mindateMMDDYYYY = ''
        if mindate:
            mindateMMDDYYYY = '%s-%s-%s' % (mindate[5:7], mindate[8:10], mindate[:4])
        params['OldStartFilingDate'] = mindateMMDDYYYY
        params['OldEndFilingDate'] = datetime.datetime.today().strftime('%m-%d-%Y')
        params['caseStartFilingDate'] = mindateMMDDYYYY
        params['caseEndFilingDate'] = datetime.datetime.today().strftime('%m-%d-%Y')
    maxpages = maxrows / 50
    dt = '9999-99-99'
    pg = 1
    output = []
    while dt >= mindate and pg <= maxpages:
        html = fetch_qry(params, pg)
        caserows = extract_caserows(html)
        if not caserows:
            break
        priorrow = ''
        for case in caserows:
            if case['CaseNumber'] in prior_cases or case['CaseNumber'] == priorrow:
                continue
            # 'FilingDate' is actually judgement date when appropriate
            if case['FilingDate'] < mindate:
                continue
            case['CaseHistory'] = fetch_casehistory(case['CaseHistoryLink'])
            parties_html = urllib2.urlopen(case['PartiesLink']).read()
            parties = extract_parties(parties_html)
            addresses = combine_parties(parties)
            for a in addresses:
                a.update(case)
                a['PartyName'] = ' & '.join(a['PartyName'])
                del a['PartiesLink']
                del a['CaseHistoryLink']
                output.append(a)
            priorrow = case['CaseNumber']
        pg += 1
        dt = caserows[-1].get('FilingDate', dt)
    return output

def last_output_filename(qry_name):
    outfiles = os.listdir('output/')
    outfiles = filter(lambda fname: qry_name in fname, outfiles)
    if outfiles == []:
        return None
    else:
        return max(outfiles)

def get_prior_cases(last_filename):
    if not last_filename:
        return []
    last_filename = 'output/' + last_filename
    last_outfile = open(last_filename).read()
    rows = last_outfile.split('\n')
    cases = []
    for row in rows:
        cases.append(row.split('\t')[0])
    return cases

def dict_to_list(d):
    return [
        d['CaseNumber'],
        d['County'],
        d['CourtLocation'],
        d['CaseType'],
        d['FilingDate'],
        d['PartyType'],
        d['PartyName'],
        d['Address'],
        d['Address2'],
        d['City'],
        d['State'],
        d['ZipCode']]

def meets_filters(address, qry):
    must_contain = qry.get('DescMustContain')
    must_not_contain = qry.get('DescMustNotContain')
    desc = address['CaseHistory'].lower()
    for phrase in must_not_contain:
        if phrase.lower() in desc:
            return False
    for phrase in must_contain:
        if phrase.lower() in desc:
            return True
    return must_contain == []

def __main__():
    print "Logging in..."
    login()
    for qry in queries.QUERIES:
        qry_name = qry['QueryName']
        print "Starting query %s..." % qry_name
        print "    ...fetching previous run..."
        last_filename = last_output_filename(qry_name)
        if last_filename:
            prior_cases = get_prior_cases(last_filename)
            last_run_date = last_filename[-20:-4]
        else:
            prior_cases = []
            last_run_date = '1900-00-00-00-00'
        print "    ...starting new run..."
        addresses = run_query(qry, mindate=last_run_date, prior_cases=prior_cases)
        timestamp = datetime.datetime.today().strftime('%Y-%m-%d-%H-%M')
        print "    ...outputing results..."
        fname = 'output/%s %s.txt' % (qry_name, timestamp)
        outfile = open(fname, 'w')
        output_count = 0
        for address in addresses:
            if address['PartyType'] not in qry['PartyType']:
                continue
            if not meets_filters(address, qry):
                continue
            newrow = '\t'.join(dict_to_list(address)) + '\n'
            outfile.write(newrow)
            output_count += 1
        outfile.close()
        print "    %s unique parties/addresses found" % len(addresses)
        print "    %s of them sent to output file" % output_count

if __name__ == '__main__':
    __main__()
