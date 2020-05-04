#!/usr/local/bin/python3

import argparse, requests, re, csv
import os, subprocess, curses
import itertools, dateparser

from math import floor
from calendar import monthrange
from pprint import pprint
from bs4 import BeautifulSoup, Tag, NavigableString
from colorama import init, Fore, Style
from dataclasses import dataclass
from datetime import datetime

base_url = "https://rexwordpuzzle.blogspot.com/feeds/posts/default"

archive_dir = "archive"

DEBUG_CONTENT = False

RE_SHORT = re.compile(r"(MON|TUE|WED|THU|FRI|SAT|SUN) (\d{1,2}-\d{1,2}-\d{1,2})", flags=re.I)
RE_LONG = re.compile(r"(Mon\.?(day)?|Tue\.?(s\.?(day)?)?|Wed\.?(nesday)?|Thu\.?((rs)\.?(day)?)?|Fri\.?(day)?|Sat\.?(urday)?|Sun\.?(day)?),? (\w{3,12}\.? \d{1,2}(,|\.) 20\d{2})", flags=re.I)

@dataclass
class Entry:
	author: str
	content: str
	comments: int
	date: datetime
	rating: int = 0
	skip: bool = False

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
				print(child.contents)
				print(Style.RESET_ALL)
			else:
				print(str(child).replace(" ", "#"))

def parse_comments(entry):
	r = r"(\d+) Comments"
	m = re.match(r, next(l for l in entry['link'] if re.match(r, l.get('title', ''))).get('title'))
	return int(m.group(1))

def parse_date(entry):
	# extract from title if possible
	title = entry['title']['$t']
	
	m_short = RE_SHORT.search(title)
	if m_short is not None:
		return dateparser.parse(m_short.group(2))

	m_long = RE_LONG.search(title)
	if m_long is not None:
		return dateparser.parse(m_long.group(12))

	print("Default to created at...")
	return datetime.fromisoformat(entry['published']['$t'])

def parse(entry):
	author = entry['author'][0]['name']['$t']
	content = entry['content']['$t']
	comments = parse_comments(entry)
	date = parse_date(entry)

	print(entry['title']['$t'], date)

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
		return local_entries

	start = datetime(year, month, 1, 0, 0, 0)
	end = datetime(year, month, monthrange(year, month)[1], hour=23, minute=59, second=59)

	params = {
		"updated-min": start.isoformat(),
		"updated-max": end.isoformat(),
		"orderby": "updated",
		"max-results": 50, # todo
		"alt": "json"
	}

	res = requests.get(base_url, params=params)
	entries = reversed([parse(entry) for entry in get_entries(res.json())])

	save_local(year, month, entries)

	return entries

def add_string(window, string, mode=0, x_offset=0):
	y, x = window.getyx()
	_, width = window.getmaxyx()

	if len(string) == 0:
		return

	split_strs = list(itertools.chain.from_iterable(zip(string.split(), itertools.repeat(' '))))[:-1]
	if string[-1].isspace():
		split_strs.append(" ")
	if string[0].isspace():
		split_strs.insert(0, " ")

	for split_str in split_strs:
		if x + len(split_str) < width:
			window.addstr(split_str, mode)
		else:
			window.addstr(y+1, x_offset, split_str, mode)
		y, x = window.getyx()

def render_entry(pad, entry, height, width, y_offset):
	pad.clear()

	author_label = "Author: "
	pad.addstr(0, 0, author_label, curses.color_pair(3))
	pad.addstr(entry.author)

	date_label = "Date: "
	pad.addstr(1, 0, date_label, curses.color_pair(3))
	pad.addstr(entry.date.strftime("%A %b %-d, %Y"))

	soup = BeautifulSoup(entry.content, 'html.parser')
	pad.move(3, 0)

	num_brs = 0
	for child in soup.children:
		y, x = pad.getyx()
		if isinstance(child, Tag):
			if child.name == "br":
				num_brs += 1
				if num_brs <= 2:
					pad.move(y+1, 0)
			else:
				num_brs = 0
				if child.name == "b":
					add_string(pad, "".join(list(child.strings)), curses.A_BOLD | curses.color_pair(2))
				if child.name == "span":
					add_string(pad, "".join(list(child.strings)), curses.color_pair(1))
				if child.name == "ul":
					for item in child.children:
						y, x = pad.getyx()
						pad.move(y+1, 0)
						add_string(pad, "".join(["- "] + list(item.strings)), curses.color_pair(3))
						y, x = pad.getyx()
						pad.move(y+1, x)
					pad.move(y+2, x)
				if child.name == "blockquote":
					pad.move(y, 3)
					add_string(pad, "".join(list(child.strings)), curses.color_pair(3), x_offset=3)
					y, x = pad.getyx()
					pad.move(y+2, 0)

		else:
			num_brs = 0
			child_str = str(child)
			add_string(pad, child_str, 0)

	pad.refresh(y_offset, 0, 1, 1, height, width)

def render_rating(window, entry):
	window.clear()

	window.addstr("Rating (1-5) (s to skip): ", curses.color_pair(3))
	if entry.skip is True:
		window.addstr("skip", curses.color_pair(2))
	elif entry.rating > 0: 
		window.addstr(str(entry.rating))

	window.refresh()

def console(stdscr, entries):
	(height, width) = stdscr.getmaxyx()
	stdscr.refresh()

	curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)
	curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
	curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)

	w_margin = 2
	h_margin = 5
	pad_width=width-w_margin
	pad_height=height-h_margin

	entry_pad = curses.newpad(1000, pad_width)

	rating_window = curses.newwin(2, pad_width, height-2, 1)

	index = 0
	y_offset = 0
	while True:
		old_index = index
		entry = entries[index]
		render_entry(entry_pad, entry, pad_height, pad_width, y_offset)
		render_rating(rating_window, entry)

		c = stdscr.getch()
		if c == ord("p"):
			index = max(0, index-1)
		if c == ord("n") or c == curses.KEY_ENTER or c == 10: # \n
			index = min(len(entries)-1, index+1)
		if c == ord("s"):
			entry.skip = True
		if ord("1") <= c <= ord("5"):
			entry.rating = int(chr(c))
		if c == curses.KEY_DOWN:
			y_offset += 1
		if c == curses.KEY_UP:
			y_offset = max(y_offset-1, 0)

		if old_index != index:
			y_offset = 0


'''
todo:
1. skip!
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

	if not DEBUG_CONTENT:
		curses.wrapper(console, entries)


