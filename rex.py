#!/usr/local/bin/python3

import argparse, requests, re, csv
import os, subprocess, curses
import itertools

from math import floor
from calendar import monthrange
from pprint import pprint
from bs4 import BeautifulSoup, Tag, NavigableString
from colorama import init, Fore, Style
from dataclasses import dataclass
from datetime import datetime

base_url = "https://rexwordpuzzle.blogspot.com/feeds/posts/default"

archive_dir = "archive"

@dataclass
class Entry:
	author: str
	content: str
	comments: int
	date: datetime
	rating: int = 0

	def write(self, f): 
		writer = csv.writer(f)
		writer.writerow([self.author, self.content, self.comments, self.date])

	@staticmethod
	def read(f):
		reader = csv.reader(f)
		row = reader.__next__()
		return Entry(author=row[0], content=row[1], comments=row[2], date=datetime.fromisoformat(row[3]))

	def print(self):
		soup = BeautifulSoup(self.content, 'html.parser')
		for child in soup.children:
			if isinstance(child, Tag):
				print(Fore.RED + child.name)
				print(str(child.string).replace(" ", "#"))
				print(Style.RESET_ALL)
			else:
				print(str(child).replace(" ", "#"))

def parse_comments(entry):
	r = r"(\d+) Comments"
	m = re.match(r, next(l for l in entry['link'] if re.match(r, l.get('title', ''))).get('title'))
	return int(m.group(1))

def parse_date(entry):
	#todo: extract from title if possible
	return datetime.fromisoformat(entry['published']['$t'])

def parse(entry):
	author = entry['author'][0]['name']['$t']
	content = entry['content']['$t']
	comments = parse_comments(entry)
	date = parse_date(entry)

	return Entry(author=author, content=content, comments=comments, date=date)

def get_entries(res):
	return res['feed']['entry']

def load_local(year, month):
	dir_path = os.path.join(archive_dir, str(year), str(month))
	if not os.path.exists(dir_path):
		return None

	entries = []
	for fname in os.listdir(dir_path):
		with open(os.path.join(dir_path, fname), 'r') as f:
			entries.append(Entry.read(f))

	return entries

def save_local(year, month, entries):
	dir_path = os.path.join(archive_dir, str(year), str(month))
	if not os.path.exists(dir_path):
		os.makedirs(dir_path)

	for entry in entries:
		fname = os.path.join(dir_path, "{0}.entry".format(entry.date.day))
		with open(fname, 'w') as f:
			entry.write(f)

def load(year, month):
	local_entries = load_local(year, month)
	if local_entries is not None:
		# local_entries[0].print()
		return local_entries

	start = datetime(year, month, 1, 0, 0, 0)
	end = datetime(year, month, monthrange(year, month)[1], hour=23, minute=59, second=59)

	params = {
		"updated-min": start.isoformat(),
		"updated-max": end.isoformat(),
		"orderby": "updated",
		"max-results": 1, # todo
		"alt": "json"
	}

	res = requests.get(base_url, params=params)
	entries = [parse(entry) for entry in get_entries(res.json())]

	save_local(year, month, entries)

	return entries

def add_string(window, string, mode):
	y, x = window.getyx()
	_, width = window.getmaxyx()

	split_strs = list(itertools.chain.from_iterable(zip(string.split(), itertools.repeat(' '))))[:-1]
	if string[-1].isspace():
		split_strs.append(" ")
	if string[0].isspace():
		split_strs.insert(0, " ")

	for split_str in split_strs:
		if x + len(split_str) < width:
			window.addstr(split_str, mode)
		else:
			# assume never exceeds window height
			window.addstr(y+1, 0, split_str, mode)
		y, x = window.getyx()

def render_entry(window, entry):
	window.clear()

	author_label = "Author: "
	window.addstr(0, 0, author_label, curses.color_pair(3))
	window.addstr(entry.author)

	date_label = "Date: "
	window.addstr(1, 0, date_label, curses.color_pair(3))
	window.addstr(entry.date.strftime("%A %b %-d, %Y"))

	soup = BeautifulSoup(entry.content, 'html.parser')
	window.move(3, 0)

	num_brs = 0
	for child in soup.children:
		y, x = window.getyx()
		if isinstance(child, Tag):
			if child.name == "br":
				num_brs += 1
				if num_brs <= 2:
					window.move(y+1, 0)
			else:
				num_brs = 0
				if child.name == "b":
					add_string(window, "".join(list(child.strings)), curses.A_BOLD | curses.color_pair(2))
				if child.name == "span":
					add_string(window, "".join(list(child.strings)), curses.color_pair(1))
		else:
			num_brs = 0
			child_str = str(child)
			add_string(window, child_str, 0)

	window.refresh()

def render_rating(window, entry):
	window.clear()

	window.addstr("Rating (1-5): ", curses.color_pair(3))
	if entry.rating > 0: 
		window.addstr(str(entry.rating))

	window.refresh()

def console(stdscr, entries):
	(height, width) = stdscr.getmaxyx()
	stdscr.refresh()

	curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
	curses.init_color(100, 70, 70, 70)
	curses.init_pair(3, 100, curses.COLOR_BLACK)

	w_margin = 2
	h_margin = 3
	entry_window = curses.newwin(height-h_margin, width-w_margin, 1, 1)

	rating_window = curses.newwin(h_margin-1, width-w_margin, 1+height-h_margin, 1)

	index = 0
	while True:
		entry = entries[index]
		render_entry(entry_window, entry)
		render_rating(rating_window, entry)

		c = stdscr.getch()
		if c == ord("p"):
			index = max(0, index-1)
		if c == ord("n"):
			index = min(len(entries)-1, index+1)
		if ord("1") <= c <= ord("5"):
			entry.rating = int(chr(c))


'''
todo:
1. fetch all entries for a given month
2. interactive rate 1-5
3. store ratings in csv file
4. on re-rate, load csv if avail so doesn't overwrite
'''

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description = "Rex Parker data miner")
	parser.add_argument('year', type=int)
	parser.add_argument('month', type=int, choices=range(1, 13))
	args = parser.parse_args()

	init()

	entries = load(args.year, args.month)

	curses.wrapper(console, entries)


