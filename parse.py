#! /usr/bin/env python
import argparse
import camelot
import functools
import json
import os
import re
import requests
import subprocess
import sys
import tarfile
import time
import xml.etree.ElementTree

# hardcoded: sanitization table
conv = str.maketrans({ '\n': '', '\r': '', '\t': '', '\xa0': '', '\xad': '', '‐': '' })

# hardcoded: doc url
urls = {
	'intrinsics': 'https://static.docs.arm.com/ihi0073/e/IHI0073E_arm_neon_intrinsics_ref.pdf',
	'table': {
		'a78': 'https://static.docs.arm.com/102160/0300/Arm_Cortex-A78_Core_Software_Optimization_Guide.pdf',
		'a77': 'https://static.docs.arm.com/swog011050/c/Arm_Cortex-A77_Software_Optimization_Guide.pdf',
		'a76': 'https://static.docs.arm.com/swog307215/a/Arm_Cortex-A76_Software_Optimization_Guide.pdf',
		'n1':  'https://static.docs.arm.com/swog309707/a/Arm_Neoverse_N1_Software_Optimization_Guide.pdf',
		'a75': 'https://static.docs.arm.com/101398/0200/arm_cortex_a75_software_optimization_guide_v2.pdf',
		'a72': 'https://static.docs.arm.com/uan0016/a/cortex_a72_software_optimization_guide_external.pdf',
		# 'a65': 'https://static.docs.arm.com/swog010045/a/Cortex_A65_Software_Optimization_Guide_1.0.pdf',
		# 'e1':  'https://static.docs.arm.com/swog466751/a/Neoverse_E1_Software_Optimization_Guide_1.0.pdf',
		'a57': 'https://static.docs.arm.com/uan0015/b/Cortex_A57_Software_Optimization_Guide_external.pdf',
		'a55': 'https://static.docs.arm.com/epm128372/30/arm_cortex_a55_software_optimization_guide_v3.pdf'
	},
	'desc': 'https://developer.arm.com/-/media/developer/products/architecture/armv8-a-architecture/2020-03/A64_ISA_xml_v86A-2020-03.tar.gz'
}


# logger
starttime = time.monotonic()
def message(msg):
	sys.stderr.write('[{:08.3f}] {}\n'.format(time.monotonic() - starttime, msg))
	return

def error(msg):
	message('error: {}'.format(msg))
	return


# utils
def to_filename(url, base):
	return(base + '/' + url.split('/')[-1])

def canonize_doc_list(docs):
	doc_str = ','.join(docs)
	return([x.split('.') for x in doc_str.split(',')])

def build_doc_list():
	def iterate_items(e):
		if type(e) is str: return([[e]])
		return(sum([[[k] + x for x in iterate_items(v)] for k, v in e.items()], []))
	return(['.'.join(x[:-1]) for x in iterate_items(urls)])


# fetch
def fetch_file(url, base = '.', verify = True):
	# check the directory where pdf might have been saved already
	path = to_filename(url, base)
	if os.path.exists(path): return(path)

	# if not, download it
	def fetch_file_intl(url, verify):
		with requests.get(url, verify = verify) as r:
			f = open(path, 'wb')
			f.write(r.content)
			f.close()

	try:
		fetch_file_intl(url, verify)
	except(requests.exceptions.SSLError):
		message('certificate verify failed. trying again without verification...')
		fetch_file_intl(url, False)
	time.sleep(1)
	return(path)


# parse
def parse_insn_table(path, range = 'all'):
	# load table
	table = camelot.read_pdf(path, pages = range)

	def parse_paren(ops_str):
		# 'add{s}' -> ['add', 's']
		m = re.match(r'(.+){(.+)}', ops_str)

		# remove '(2)' at the tail
		if m == None: return([ops_str.split('(')[0].strip(' ')])

		# ['add', 's'] -> ['add', 'adds']
		base = m.group(1).strip(' ')
		ext  = m.group(2).strip(' ')
		return([base, base + ext])

	def parse_ops(ops_str):
		a = sum([parse_paren(x.strip(' ')) for x in ops_str.split(',')], [])
		return(a)

	def parse_form(var_str):
		var_elems = [x.lower() for x in re.split(r'\W+', var_str)]
		if 'asimd'  in var_elems: return 'vector'
		if 'simd'   in var_elems: return 'vector'
		if 'vector' in var_elems: return 'vector'
		if 'crypto' in var_elems: return 'vector'
		if 'vfp'    in var_elems: return 'vector'
		return('scalar')

	def parse_variant(var_str):
		return([x.strip(' ') for x in var_str.split(',')])

	# parse table into opcode -> (form, latency, throughput, pipes, notes) mappings
	insns = dict()
	for t in table:
		df = t.df.applymap(lambda x: x.translate(conv).lower())
		if not df[0][0].startswith('instruction'): continue
		if not df[1][0].startswith('aarch64'): continue
		ops = sum([[(op, r) for op in parse_ops(r[1])] for i, r in df.iterrows() if i != 0], [])
		for op, r in ops:
			if op not in insns: insns[op] = []
			insns[op].append({
				'form':    parse_form(r[0]),
				'variant': parse_variant(r[0]),
				'latency':    r[2],
				'throughput': r[3],
				'pipes':      r[4],
				'notes':      r[5]
			})
	return(insns)

def parse_intrinsics(path, range = 'all'):
	# load table
	table = camelot.read_pdf(path, pages = range)

	def parse_op_var(mnemonic_str):
		return(mnemonic_str.split(' ')[0])

	def parse_op(mnemonic_str, intr_str):
		op = parse_op_var(mnemonic_str)
		return(op if op in intr_str else op.strip('2'))		# remove tail '2' for '_high' variants

	def parse_form(mnemonic_str):
		is_vec = functools.reduce(lambda x, y: x or y.startswith('v'), mnemonic_str.split(' ')[1:], False)
		return('vector' if is_vec else 'scalar')

	def parse_type(intr_str):
		return(intr_str.split(' ')[1].split('(')[0].split('_')[-1])

	# parse table into opcode -> (intrinsic, arguments, mnemonic, result) mappings
	insns = dict()
	for t in table:
		df = t.df.applymap(lambda x: x.translate(conv).lower())
		if not df[0][0].startswith('intrinsic'): continue
		ops = [(parse_op(r[2], r[0]), r) for i, r in df.iterrows() if i != 0]
		for op, r in ops:
			if op not in insns: insns[op] = []
			insns[op].append({
				'form':   parse_form(r[2]),
				'type':   parse_type(r[0]),
				'op_var': parse_op_var(r[2]),
				'intrinsic': r[0],
				'mnemonic':  r[2]
			})
	return(insns)

def parse_insn_xml(path):
	tar = tarfile.open(path)
	files = [x.name for x in filter(lambda x: x.name.endswith('.xml'), tar.getmembers())]

	def parse_op_base(ops_str):
		m = re.match(r'[\w, ]+', ops_str)
		if m == None: return(None, ops_str)
		ops = [x.strip(' ') for x in m.group(0).strip(' ').split(',')]
		ops = functools.reduce(lambda x, y: x if x[-1] + '2' == y else x + [y], ops[1:], [ops[0]])
		return(ops, ops_str[m.end(0):])

	def parse_op_attr(ops_str):
		m = re.match(r'\([\w, ]+\)', ops_str)
		if m == None: return('', ops_str)
		return(m.group(0).strip('( )'), ops_str[m.end(0):])

	def parse_ops(root):
		ops_str = root.findall('./heading')[0].text.lower()
		ops = []
		while len(ops_str) > 0:
			(base, ops_str) = parse_op_base(ops_str)
			if base == None: break
			(attr, ops_str) = parse_op_attr(ops_str)
			ops.extend([(op, attr) for op in base])
		return(ops)

	def parse_cat_tree_intl(node, acc):
		if node.text != None: acc += node.text
		for c in node: acc = parse_cat_tree_intl(c, acc)
		if node.tail != None: acc += node.tail
		return(acc)

	def parse_cat_tree(node):
		s = parse_cat_tree_intl(node, '').translate(conv)
		return(re.sub(r'\s+', ' ', s).strip('\r\n\t '))

	def parse_brief(root):
		return(parse_cat_tree(root.findall('./desc/brief')[0]))

	def parse_description(root):
		keys = ['./desc/description', './desc/authored']
		for key in keys:
			m = root.findall(key)
			if len(m) > 0: return(parse_cat_tree(m[0]))
		return('')

	def parse_iclass(root, op):
		attr = dict()
		for x in root.findall('./classes/iclass/docvars/docvar'):
			attr[x.attrib['key']] = x.attrib['value']
		if len(attr) == 0: print(op, 'not found')
		print(op, attr)
		return(attr)

	insns = dict()
	for x in files:
		content = b''.join([x for x in tar.extractfile(x).readlines()])
		root = xml.etree.ElementTree.fromstring(content.decode('UTF-8'))
		if root.tag != 'instructionsection': continue
		ops    = parse_ops(root)
		brief  = parse_brief(root)
		desc   = parse_description(root)
		iclass = parse_iclass(root, ops[0][0])
		for op, attr in ops:
			if op not in insns: insns[op] = []
			insns[op].append({
				'attr':   attr,
				'brief':  brief,
				'desc':   desc,
				'iclass': iclass
			})
	return(insns)


# fetch -> parse -> concatenate
def fetch_all(doc_list, base = '.'):
	docs = canonize_doc_list(doc_list)
	for doc in docs:
		if not doc[0] in urls:
			error('unknown document specifier: --doc={}'.format(doc[0]))
			continue

		if type(urls[doc[0]]) is str:
			message('fetching {}... ({})'.format(doc[0], urls[doc[0]]))
			fetch_file(urls[doc[0]], base)
			continue

		archs = urls[doc[0]].keys() if len(doc) == 1 else [doc[1]]
		for arch in archs:
			message('fetching {}.{}... ({})'.format(doc[0], arch, urls[doc[0]][arch]))
			fetch_file(urls[doc[0]][arch], base)
	return(None)

def parse_one(doc, base = '.'):
	if not doc[0] in urls:
		error('unknown document specifier: --doc={}'.format(doc[0]))
		return(None)

	def to_filename_with_check(url, base):
		path = to_filename(url, base)
		if not os.path.exists(path):
			error('file not found: {} (might be \'--dir\' missing or wrong)'.format(path))
			return(None)
		return(path)

	if type(urls[doc[0]]) is str:
		fn = parse_insn_xml if doc[0] == 'desc' else parse_intrinsics
		path = to_filename_with_check(urls[doc[0]], base)
		return(fn(path) if path != None else None)

	if len(doc) == 1 or doc[1] not in urls[doc[0]]:
		error('second specifier needed for --doc=table, one of [\'a78\', \'a77\', \'a76\', \'n1\', \'a75\', \'a72\', \'a57\', \'a55\']')
		return(None)
	path = to_filename_with_check(urls[doc[0]][doc[1]], base)
	return(parse_insn_table(path) if path != None else None)

def parse_all(doc_list, base = '.'):
	docs = canonize_doc_list(doc_list)
	if len(docs) == 1: return(parse_one(docs[0], base))

	insns = dict()
	def update_dict(dic, ks, v):
		if len(ks) == 1:
			dic[ks[0]] = v
			return(dic)
		if ks[0] not in dic: dic[ks[0]] = dict()
		dic[ks[0]] = update_dict(dic[ks[0]], ks[1:], v)
		return(dic)

	for doc in docs:
		doc_str = '.'.join(doc)
		cmd = '{} {} parse --doc={} --dir={}'.format(sys.executable, os.path.realpath(sys.argv[0]), doc_str, base)
		message('parsing {}... (command: {})'.format(doc_str, cmd))
		ret = subprocess.run(cmd, shell = True, capture_output = True)
		ops = json.loads(ret.stdout)
		for k, v in ops.items(): insns = update_dict(insns, [k] + doc, v)
	return(insns)


if __name__ == '__main__':
	ap = argparse.ArgumentParser(
		description = 'fetch and parse AArch64 ISA and intrinsics documentation'
	)

	# subcommands
	sub = ap.add_subparsers()
	fa = sub.add_parser('fetch')
	fa.set_defaults(func = fetch_all)
	fa.add_argument('--dir',
		action  = 'store',
		help    = 'working directory where downloaded documents are saved',
		default = '.'
	)
	fa.add_argument('--doc',
		action  = 'append',
		help    = 'list of documents to fetch, one or more of [\'intrinsics\', \'table\', \'desc\']',
		default = []
	)

	pa = sub.add_parser('parse')
	pa.set_defaults(func = parse_all)
	pa.add_argument('--dir',
		action  = 'store',
		help    = 'working directory where downloaded documents are saved',
		default = '.'
	)
	pa.add_argument('--doc',
		action  = 'append',
		help    = 'list of documents to fetch, one or more of [\'intrinsics\', \'table\', \'desc\']',
		default = []
	)

	args = ap.parse_args()
	if args.doc == []: args.doc = build_doc_list()
	if not os.path.exists(args.dir): os.makedirs(args.dir)

	ret = args.func(args.doc, args.dir)
	if ret != None: print(json.dumps(ret))

	# fetch_all()
	# insns = parse_all()
	# insns = parse_insn_table(to_filename(urls['table']['a55'], '.'))
	# insns = parse_intrinsics(to_filename(urls['intrinsics'], '.'))



