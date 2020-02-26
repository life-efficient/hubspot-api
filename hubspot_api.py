from selenium import webdriver
import json
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from time import sleep, time
import random
import re
import numpy as np
import boto3

s3 = boto3.resource('s3')

import sys, os
sys.path.append(os.path.expanduser('~/projects/bots'))
from bots import Bot

max_time = 10

def enroll_all(account_id, sequence_id, emails):
    bot = EnrollBot(account_id, sequence_id)
    bot.enroll_all(emails, sequence_id)

class EnrollBot(Bot):
    def __init__(self, account_id, sequence_id):
        already_enrolled_key = f'already_enrolled/{sequence_id}'.split('.')[0] + '.json'
        errors_filename = f'errors/{sequence_id}'.split('.')[0] + '.json'
        self.account_id = account_id
        super().__init__()
        try:
            self.errors = json.load(open(errors_filename))
        except:
            print('error getting errors filename')
            self.errors = {}
        try:
            self.already_enrolled_file = s3.Object('hubspot-api', already_enrolled_key) # get remote file with already enrolled
            self.already_enrolled = self.already_enrolled_file.get()
        except:# FileNotFoundError as e:
            print('The already enrolled file must not yet exist')
            self.already_enrolled = []
        print(self.already_enrolled)

    def enroll_all(self, contacts, sequence_id):
        for idx, contact in contacts.iterrows():
            contact = dict(contact)

            # CHECK NOT ALREADY ENROLLED
            print(f'\n{idx}/{len(contacts)} Enrolling {contact["Email"]}')
            if contact['Email'] in self.already_enrolled:
                print(f'{contact["Email"]} is already enrolled')
                continue

            # GO TO SEQUENCE AND SEARCH FOR CONTACT
            self.driver.get(f'https://app.hubspot.com/sequences/{self.account_id}/sequence/' + sequence_id) # go to webpage
            sleep(1)
            self.click_btn('enroll')
            self.click_btn('enroll a single contact')
            self.search(contact['Email'])
            sleep(2)
            self.driver.find_element_by_xpath('//tr[@class="pointer"]').click()
            self.click_btn('next')
            sleep(3)

            # REPLACE REPLACEABLE MISSING TOKENS
            src = self.driver.page_source.lower()
            if 'missing tokens' in src:
                danger_boxes = self.driver.find_elements_by_class_name('tag-danger')
                danger_boxes = [d for d in danger_boxes if d.text != '']
                missing_tokens = list(set([d.text for d in danger_boxes]))
                print('missing tokens:', missing_tokens)
                unresolved_tokens = False
                for d in range(len(missing_tokens)):
                    if missing_tokens[d] == 'Contact: Company Name':
                        try:
                            company_name = contact['Name']
                            print(f'replacing company name with {company_name}')
                            danger_boxes[d].click()
                            self.search(company_name, _type='text', placeholder='Enter contact: company name')
                            self.click_btn('update all')
                        except KeyError:
                            print('No replacement company name found')
                            unresolved_tokens = True
                    if missing_tokens[d] == 'Contact: First Name':
                        try:
                            replacement = 'there'
                            print(d)
                            print(f'replacing name with {replacement}')
                            print(danger_boxes[d])
                            print(danger_boxes[d].text)
                            danger_boxes[d].click()
                            self.search(replacement, _type='text', placeholder='Enter contact: first name')
                            self.click_btn('update all')
                        except KeyError:
                            print('No replacement name found')

                if unresolved_tokens:
                    err = 'This contact is missing tokens: '
                    err += ', '.join(missing_tokens)
                    print(err)
                    self.errors.update({contact['Email']: err})
                    with open(errors_filename, 'w+', encoding='utf-8') as f:
                        json.dump(self.errors, f, ensure_ascii=False, indent=4)
                    continue

            # BEGIN SEQUENCE
            self.click_btn('start sequence')

            # ADD CONTACT TO LIST OF ALREADY ENROLLED
            self.already_enrolled.append(contact['Email'])
            self.already_enrolled_file.put(Body=json.dumps(self.already_enrolled))
            sleep(1)