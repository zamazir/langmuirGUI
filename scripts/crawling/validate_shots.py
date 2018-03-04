"""
Validate shots in a list of shot numbers by crawling the AUG journal
"""
import scrapy
from w3lib.http import basic_auth_header

class ShotValidator(scrapy.Spider):
    name = "valid_shots"
    useful_shots = []

    def get_shot_numbers(self):
        shotnumbers = []
        with open("tdiv_results.txt", "r") as f:
            for line in f.readlines():
                shotnumbers.append(line.split()[0])
        return shotnumbers

    def authenticate(self):
        user = raw_input("User name: ")
        password = raw_input("Password: ")
        auth = basic_auth_header(user, password)
        return auth

    def start_requests(self):
        auth = self.authenticate()
        for shotnr in self.get_shot_numbers():
            url = ("https://www.aug.ipp.mpg.de/cgibin/local_or_pass/" +
                   "journal.cgi?shot=" + shotnr)
            yield scrapy.Request(url=url, headers={'Authorization': auth},
                                 callback=self.parse)

    def parse(self, response):
        query_type = "//div/i[.='Type:']/following-sibling::span/text()[1]"
        query_useful = "//div/i[.='Useful:']/following-sibling::span/text()[1]"

        type = response.xpath(query_type).extract_first()
        useful = response.xpath(query_useful).extract_first()
        shotnr = response.url.split('=')[-1]

        if type == 'plasma' and useful == 'yes':
            self.useful_shots.append(shotnr)
            yield{'shotnr': shotnr}

    def closed(self, reason):
        with open("tdiv_results.txt", "r") as f:
            lines = f.readlines()

        with open("tdiv_results_analysed.txt", "w") as f:
            for line in lines:
                shotnr = line.split()[0]
                if shotnr in self.useful_shots:
                    f.write(line.rstrip() + " useful\n")
                else:
                    f.write(line)
