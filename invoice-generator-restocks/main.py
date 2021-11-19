import requests, json, time, re, traceback, os, uuid
from datetime import datetime
from bs4 import BeautifulSoup
from InvoiceGenerator.pdf import SimpleInvoice
from InvoiceGenerator.api import Invoice, Item, Client, Provider, Creator

### GENERAL LOADING UP ###
config = json.load(open('config.json'))
### LOAD IN USER DATA ###
email = config['email']
password = config['password']
user_region = config['restocks_region']
vat_percentage = config['vat_percentage']
vat_business_id = config['vat_business_id']
company_name = config['company_name']
address = config['address']
city = config['city']
postal_code = config['postal_code']
country = config['country']
personal_name = config['company_name']
currency = config['currency']


### FUNCTIONS ###
def make_cookie_str(session):
    s = ''
    for k,v in dict(session.cookies).items():
        s += f'{k}={v}; '
    s = s[:-2]
    return s

def get_cookies(session):
    response = session.get("https://restocks.net/login")
    csrf_token = ''
    try:
        csrf_token = re.findall(r'<meta name="csrf-token" content="([0-9A-Za-z]*)">', response.text)[0]
        print(f"Found CSRF: {csrf_token}")
    except:
        csrf_token = None
    return csrf_token

def login(session, csrf):
    headers = {
        'authority': 'restocks.net',
        'cache-control': 'max-age=0',
        'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="96", "Google Chrome";v="96"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'upgrade-insecure-requests': '1',
        'origin': 'https://restocks.net',
        'content-type': 'application/x-www-form-urlencoded',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-user': '?1',
        'sec-fetch-dest': 'document',
        'cookies': make_cookie_str(session),
        'referer': f'https://restocks.net/{user_region}/login',
        'accept-language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
        'dnt': '1'
    }
    payload = {
        "_token": csrf,
        "email": email,
        "password": password
    }
    response = session.post(f"https://restocks.net/{user_region}/login", headers = headers, data = payload)
    if response.url == f"https://restocks.net/{user_region}":
        print(f"LOGIN SUCCESSFUL!")
    else:
        raise ValueError("Can not login, check config!")
        print(f"LOGIN FAILED")

def scraping_sales(session):
    raw_sales_data = ''
    page = 1
    while True:
        response = session.get(f"https://restocks.net/{user_region}/account/sales/history?page={page}")
        if "no__listings__notice" in response.text:
            break
        else:
            formatted_str = re.sub(r'\\n', '', response.text)
            raw_sales_data += json.loads(formatted_str)["products"]
            page += 1
    return raw_sales_data

def preprocess_data(raw_sales_data):
    raw_sales_data = re.sub(r'\\', '', raw_sales_data)
    raw_sales_data = re.sub(r"<br/>", "", raw_sales_data)
    raw_sales_data = re.sub(r"<span>", "", raw_sales_data)
    raw_sales_data = re.sub(r"</span>", "", raw_sales_data)
    raw_sales_data = re.sub(r"     ", "", raw_sales_data)
    raw_sales_data = re.sub(r"                ", " ", raw_sales_data)
    preprocessed_data = re.sub(r"            ", "", raw_sales_data)
    all_sales = BeautifulSoup(preprocessed_data, "lxml").find_all("tr")
    return all_sales


def generate_invoice(invoice_info):
    vat_percentage, vat_business_id, company_name, address, city, postal_code, country, personal_name, currency, item, sale_id, price, date, unique_id = invoice_info
    
    price_tax = price/(1+vat_percentage/100)
    
    os.environ['INVOICE_LANG'] = 'en'
    
    client = Client(summary='Restocks B.V.', address='Veldsteen 19', city='Breda', zip_code='4815 PK', vat_id='NL 859756257B01', country='the Netherlands')
    provider = Provider(summary=company_name,address=address, city=city, zip_code=postal_code, vat_id=vat_business_id) 
    creator = Creator(personal_name)
    
    invoice = Invoice(client, provider, creator)
    invoice.number = date
    invoice.use_tax = True
    invoice.currency = '€'

    invoice.add_item(Item(count=1, price=price_tax, description=item, tax=vat_percentage))

    pdf = SimpleInvoice(invoice).gen(f'{date.replace("/","-")} - {unique_id}.pdf', generate_qr_code=False)


def processing_invoice(all_sales):
    count = 1
    for sale in all_sales[1:]:
        sale = str(sale)
        sale = sale.replace('<td>', "pause")
        sale = sale.replace('</td>', "pause")
        sale = sale.replace('<br/>', "pause")
        
        parsed_sale = [i for i in sale.split("pause") if len(i) > 1]

        item = parsed_sale[2].strip()
        sale_id = parsed_sale[3].strip()
        price = float((parsed_sale[4].replace("€", "").strip()))
        date = parsed_sale[5].strip()
        unique_id = uuid.uuid1()

        invoice_info = [vat_percentage, vat_business_id, company_name, address, city, postal_code, country, personal_name, currency, item, sale_id, price, date, unique_id]
        
        generate_invoice(invoice_info)
        print(f'Generated invoice {count}/{len(all_sales[1:])}')
        
        count += 1

def main():
    session = requests.session()
    try:
        token = get_cookies(session)
        if token == None:
            raise ValueError('Can not find CSRF')
        login(session, token)
        raw_sales_data = scraping_sales(session)
        all_sales = preprocess_data(raw_sales_data)
        os.makedirs(f"./invoices/{datetime.now().strftime('%Y-%m-%d %H.%M.%S')}")
        os.chdir(f"./invoices/{datetime.now().strftime('%Y-%m-%d %H.%M.%S')}")
        processing_invoice(all_sales)
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.format_exc())
        print("Can not proceed with generating invoices")

main()