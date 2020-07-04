#! /usr/bin/env python
import argparse
import camelot
import functools
import itertools
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
conv_singleline = str.maketrans({ '\t': '', '\xa0': '', '\xad': '', '‐': '', '\n': '', '\r': '' })
conv_multiline  = str.maketrans({ '\t': '', '\xa0': '', '\xad': '', '‐': '' })

# hardcoded: doc url
urls = {
	'description': 'https://developer.arm.com/-/media/developer/products/architecture/armv8-a-architecture/2020-03/A64_ISA_xml_v86A-2020-03.tar.gz',
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
	'macros': 'https://static.docs.arm.com/101028/0011/ACLE_Q2_2020_101028_Final.pdf'
}
macro_page_range = '34-39'			# make sure the range covers entire list of feature macros


# canonize opcode for use as matching tags
def canonize_opcode(op_raw):
	fallback = {
		'vmov':      'xtn',
		'sra':       'ssra',
		'revsh':     'rev',
		'stadda':    'stadd',
		'stclra':    'stclr',
		'steora':    'steor',
		'stseta':    'stset',
		'stsmaxa':   'stsmax',
		'stsmina':   'stsmin',
		'stumaxa':   'stumax',
		'stumina':   'stumin',
		'staddal':   'staddl',
		'staddalb':  'staddlb',
		'staddalh':  'staddlh',
		'stclral':   'stclrl',
		'stclralb':  'stclrlb',
		'stclralh':  'stclrlh',
		'steoral':   'steorl',
		'steoralb':  'steorlb',
		'steoralh':  'steorlh',
		'stsetal':   'stsetl',
		'stsetalb':  'stsetlb',
		'stsetalh':  'stsetlh',
		'stsmaxal':  'stsmaxl',
		'stsmaxalb': 'stsmaxlb',
		'stsmaxalh': 'stsmaxlh',
		'stsminal':  'stsminl',
		'stsminalb': 'stsminlb',
		'stsminalh': 'stsminlh',
		'stumaxal':  'stumaxl',
		'stumaxalb': 'stumaxlb',
		'stumaxalh': 'stumaxlh',
		'stuminal':  'stuminl',
		'stuminalb': 'stuminlb',
		'stuminalh': 'stuminlh'
	}
	if op_raw in fallback: return(fallback[op_raw])
	return(re.split(r'[0-9\W\.]+', op_raw.strip('0123456789 '))[0])

# __ARM_FEATURE tag -> "ARMv8.n.<feature>" conversion
feature_abbrev = {
	'crc32': 'crc',
	'sha2':  'sha2',
	'sha3':  'sha3',
	'sm3':   'sm3',
	'sm4':   'sm4',
	'bf16':  'bf16',
	'fp16':  { 'scalar': 'fp16', 'fml': 'fhm' },
	'qrdmx': 'rdma',
	'jcvt':  'jconv',
	'dotprod': 'dotprod',
	'complex': 'compnum',
	'matmul':  'i8mm',
	'frint':   'frint'
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
def to_filepath(url, base):
	return(base + '/' + url.split('/')[-1])

def extract_filename(path):
	return(path.split('/')[-1])

def extract_base(path):
	return('/'.join(path.split('/')[:-1]))

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
	path = to_filepath(url, base)
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
def parse_insn_table(path, page_range = 'all'):
	# I suppose all opcodes appear in the table is in the canonical form. so no need for canonizing them.
	def parse_opcodes(ops_str):
		def parse_paren(ops_str):
			m = re.match(r'(.+)[\({](.+)[\)}]', ops_str)		# 'add{s}' -> ['add', 's']
			(base, ext) = (m.group(1), m.group(2)) if m != None else (ops_str, '')		# ['add', 's'] -> ['add', 'adds']
			return([(canonize_opcode(x), x) for x in { base.strip(' '), base.strip(' ') + ext.strip(' ') }])

		a = sum([parse_paren(x.strip(' ')) for x in re.split(r'[,/]+', ops_str)], [])
		return(a)

	def parse_iclass_itype(var_str):
		var_elems = [x.lower() for x in re.split(r'\W+', var_str)]
		if 'asimd'  in var_elems: return('asimd', 'any')		# too many variants in asimd
		if 'simd'   in var_elems: return('asimd', 'any')
		if 'vector' in var_elems: return('asimd', 'any')
		if 'crypto' in var_elems: return('asimd', 'vector')		# crypto is always asimd-vector
		if 'vfp'    in var_elems: return('asimd', 'vector')		# two types for FP subclass: vector,
		if 'fp'     in var_elems: return('float', 'scalar')		#                            and scalar
		return('general', 'scalar')								# no instruction classified as general-vector

	def parse_variant(var_str):
		return([x.strip(' ') for x in var_str.split(',')])

	# load table
	tables = camelot.read_pdf(path, pages = page_range)

	# parse table into opcode -> (form, latency, throughput, pipes, notes) mappings
	insns = dict()
	for t in tables:
		df = t.df.applymap(lambda x: x.translate(conv_singleline).lower())
		if not df[0][0].startswith('instruction'): continue
		if not df[1][0].startswith('aarch64'): continue
		ops = sum([[(op_canon, op_raw, r) for op_canon, op_raw in parse_opcodes(r[1])] for i, r in df.iterrows() if i != 0], [])
		for op_canon, op_raw, r in ops:
			if op_canon not in insns: insns[op_canon] = []
			(iclass, itype) = parse_iclass_itype(r[0])
			variant = parse_variant(r[0])
			insns[op_canon].append({
				'op_raw':  op_raw,
				'iclass':  iclass,								# for matching with intrinsics and description
				'itype':   itype,								# for matching with intrinsics and description
				'variant': variant,								# to describe differences in the same <iclass>-<itype> class
				'latency':    r[2],
				'throughput': r[3],
				'pipes':      r[4],
				'notes':      r[5],
				'page':    t.page
			})
	meta = { 'path': path }
	return({ 'metadata': meta, 'insns': insns })




def parse_intrinsics(path, page_range = 'all'):
	# reconstruct instruction sequence from joined string
	def recompose_sequence(asm_str):
		parts  = asm_str.split(' ')
		delims = '+-*/%=(){}[]'
		(bin, join_more) = ([parts[0]], False)
		for p in parts[1:]:
			if p == '(scalar)': continue						# workaround for FABD (scalar) Hd,Hn,Hm
			if join_more or p in delims:
				bin[-1] += ' ' + p
				join_more = True
			else:
				bin.append(p)
				join_more = False
		return(list(zip(bin[::2], (bin[1:] + [''])[::2])))		# list of (opcode operands) pairs

	# canonize opcode for use as matching tags
	def extract_opcode(intr_str, seq_canon):
		# tentative raw opcode and form parsed from the first one
		op_raw = seq_canon[0][0]								# opcode of the first element of (opcode, operands) list
		# if expanded sequence is complex, try extract representative from function declaration
		if op_raw.startswith('result') or len(seq_canon) > 1:
			op_raw = re.split(r'[\W()]+', intr_str)[1].split('_')[0]
			if op_raw[0]  == 'v': op_raw = op_raw[1:]			# almost all function names begin with 'v'
			if op_raw[0]  == 'q': op_raw = op_raw[1:]			# workaround for vqtbx
			if op_raw[-1] == 'q': op_raw = op_raw[:-1]			# 128bit-form
		# canonical opcode for matching with description and tables:
		# basically op_raw is used for matching descriptions, if not found, then fallback to op_canon
		op_canon = canonize_opcode(op_raw)
		return(op_canon, op_raw)

	# extract operand form from either intrinsics declaration or sequence of instructions
	def infer_inout_form(intr_str, seq_canon):
		# infer datatype from argument strings, for distinguishing half (sometimes armv8.2-fp16) instructions from single and double
		def aggregate_datatype(type_str):
			table = {
				'uint8':  '8',  'int8': '8',  'poly8': '8',
				'uint16': '16', 'int16':'16', 'poly16':'16',
				'uint32': '32', 'int32':'32', 'poly32':'32',
				'uint64': '64', 'int64':'64', 'poly64':'64',
				'float16': 'half',   'bfloat16': 'bf16',
				'float32': 'single', 'float64':  'double'
			}
			type_base = [re.split(r'[_x]+', x)[0] for x in type_str]
			datatypes = list(set([table[x] for x in type_base if x in table]))
			return(datatypes)

		def type_to_signature(type_str):
			table = {
				'uint8':   ('b', 'b', 8),  'int8':  ('b', 'b', 8),  'poly8':  ('b', 'b', 8),
				'uint16':  ('h', 'h', 16), 'int16': ('h', 'h', 16), 'poly16': ('h', 'h', 16),
				'uint32':  ('w', 's', 32), 'int32': ('w', 's', 32), 'poly32': ('w', 's', 32),
				'uint64':  ('x', 'd', 64), 'int64': ('x', 'd', 64), 'poly64': ('x', 'd', 64),
				'float16': ('h', 'h', 16), 'bfloat16': ('h', 'h', 16),
				'float32': ('s', 's', 32), 'float64':  ('d', 'd', 64)
			}

			tbs = re.split(r'[_x]+', type_str)
			if tbs[0] == 'const': return('i')								# actually imm field (not a const variable), no datatype for imm
			if tbs[1] == 't' and tbs[0] in table: return(table[tbs[0]][0])	# fed to scalar pipe
			if tbs[1] == '1' and tbs[0] in table: return(table[tbs[0]][1])	# fed to vector (simdfp) pipe
			return('V' if int(tbs[1]) * table[tbs[0]][2] == 128 else 'v')	# packed simd

		def operand_to_signature(operand):
			if operand == '': return('-')
			if operand[0] in 'bhwxrsdq': return(operand[0])
			if operand[0] != 'v': return('-')
			# print(operand)
			return('V' if operand.split('.')[1] in ['16b', '8h', '4s', '2d', '4w', '2x'] else 'v')

		types = [x.strip(' ').split(' ')[0] for x in re.split(r'[\(\),]+', intr_str)]
		datatypes = aggregate_datatype(types)

		# if expanded sequence is complex, try extract form from function declaration
		# but this path is always fallback for emulated intrinsics, which generates multiple instructions,
		# because some instructions (loads and stores) have different arugument (operand) order between intrinsics and asmtemplate
		if len(seq_canon) > 1:
			sig = ''.join([type_to_signature(x) for x in types if x != ''])
			return(sig, datatypes)

		# simple (single-mnemonic) sequence; this path gives stable result
		if len(seq_canon) == 1:
			operands = [x.strip('{}') for x in seq_canon[0][1].split(',')]
			types  = [operand_to_signature(x) for x in operands]
			imms   = ['i' if ('[' in x and not x.startswith('[')) or x.startswith('imm') else '-' for x in operands]
			ptrs   = ['x' if '[' in x and x.startswith('[') else '-' for x in operands]
			shift  = ['i' if x.startswith('#') else '-' for x in operands]
			sig    = ''.join(filter(lambda x: x != '-', sum([list(x) for x in zip(types, imms, ptrs, shift)], [])))
			return(sig, datatypes)

		# seems nop or no-operand instruction (system?)
		return('', [])

	# take two arguments: intrinsic function declaration, and sequences of instructions after expansion
	def parse_op_insns(intr_str, seq_canon):
		(op_canon, op_raw) = extract_opcode(intr_str, seq_canon)
		(form, datatypes) = infer_inout_form(intr_str, seq_canon)
		return(op_canon, op_raw, form, datatypes)

	# load table
	tables = camelot.read_pdf(path, pages = page_range)

	# parse table into opcode -> (intrinsics, arguments, mnemonic, result) mappings
	insns = dict()
	for t in tables:
		# print(t.df)
		df = t.df.applymap(lambda x: x.translate(conv_singleline).lower())
		if not df[0][0].startswith('intrinsic'): continue
		for i, r in df.iterrows():
			if i == 0: continue
			seq_canon = recompose_sequence(r[2])
			# print(seq_canon)
			(op_canon, op_raw, form, datatypes) = parse_op_insns(r[0], seq_canon)
			if op_canon not in insns: insns[op_canon] = []
			insns[op_canon].append({
				'op_raw':    op_raw,
				'form':      form,
				'datatypes': datatypes,
				'intrinsics': r[0],
				'sequence':  [' '.join(list(x)).strip(' ') for x in seq_canon],
				'page':      t.page
			})
	meta = { 'path': path }
	return({ 'metadata': meta, 'insns': insns })




def parse_macros(path):
	def parse_macro_intl(macro_str):
		if not macro_str.startswith('__arm_feature_'): return(None, None)
		tags = macro_str[len('__arm_feature_'):].split('_')

		d = feature_abbrev
		for tag in tags:
			if tag not in d: return(None, None)
			d = d[tag]
			if type(d) is str: return(d, macro_str)
		return(None, None)

	# load table
	tables = camelot.read_pdf(path, macro_page_range)
	macros = dict()
	for t in tables:
		# print(t.df)
		df = t.df.applymap(lambda x: x.translate(conv_singleline).lower())
		if not df[0][0].startswith('macro name'): continue
		for i, r in df.iterrows():
			if i == 0: continue
			(feature, macro) = parse_macro_intl(r[0])
			if feature == None: continue
			macros[feature] = {
				'macro': macro,
				'page':  t.page
			}
	meta = { 'path': path }
	return({ 'metadata': meta, 'insns': macros })




def prepare_expanded_tarfile(path):
	tar = tarfile.open(path)
	files = [x.name for x in filter(lambda x: x.name.endswith('.xml'), tar.getmembers())]
	dirs  = sorted(list(set([x.split('/')[1] for x in files])))	# suppose starts with './'

	if len(dirs) != 2 or dirs[0] + '_OPT' != dirs[1]:
		# unknown directory structure
		return(None, None, None)

	tar_intl_xml_dir = '/'.join(['.', dirs[1]])
	files = list(filter(lambda x: x.startswith(tar_intl_xml_dir), files))

	# untar directory if needed
	if not os.path.exists(tar_intl_xml_dir):
		tar.extractall(extract_base(path))

	html_dir = '/'.join([extract_base(path), dirs[1], ''])		# use optimized-pseudocode variant
	return(html_dir, tar, files)

def parse_insn_xml(path):
	# extract and concatenate all text under a node
	def dump_text(nodes, remove_newlines = True):
		def dump_text_intl(n, acc):
			if n.text != None: acc += n.text
			for c in n: acc = dump_text_intl(c, acc)
			if n.tail != None: acc += n.tail
			return(acc)

		(conv, st) = (conv_singleline, '\t ') if remove_newlines else (conv_multiline, '\r\n\t ')
		s = ' '.join([dump_text_intl(n, '').translate(conv).strip(st) for n in nodes])
		return(re.sub(r'\s+', ' ', s) if remove_newlines else s)

	def canonize_asm(asm):
		(op_raw, operands) = tuple([x.strip(' ') for x in (asm + ' ').split(' ', 1)])
		if operands.startswith('{2}'):
			op_raw += '{2}'
			operands = operands[3:]
		if operands.startswith('<bt> <'):		# bfmlal <bt> workaround
			operands = operands[5:]
		operands = ''.join(list(filter(lambda x: x not in '<> ', operands)))
		return(' '.join([op_raw, operands]).lower())

	# instruction class and corresponding forms
	def parse_attributes(root):
		def format_form(asm):
			def parse_form(operand, rxs):
				if len(rxs) == 0: return(operand)
				operand_parts = filter(lambda x: x != '', [x.strip(' ') for x in re.split(rxs[0], operand)])
				return(list(filter(lambda x: x != [], [parse_form(x, rxs[1:]) for x in operand_parts])))

			def map_form(operands, depth):
				if depth == 0:
					if operands.startswith('#'): return(['i'])
					if operands.startswith('('): return([(operands.strip('<>()') + ' ')[0], ''])
					return([operands.strip('<>')[0]])
				e = [map_form(x, depth - 1) for x in operands]
				if depth != 1: e = [x for i, x in enumerate(e)]
				parts = [''.join(x) for x in itertools.product(*e)]
				return(list(set(parts)))

			# canonical form is ignored here; is parsed from ./desc/description
			(op_raw, operands) = tuple((asm + ' ').split(' ', 1))
			delims = [r'[\[\]]+', r'[\{\}]+', r'[, ]+']
			return(map_form(parse_form(''.join(filter(lambda x: x != ' ', operands)), delims), len(delims)))

		attrs = []
		iclasses = root.findall('./classes/iclass')
		for iclass in iclasses:
			attr = dict()
			for x in iclass.findall('./docvars/docvar'):
				attr[x.attrib['key'].lower()] = x.attrib['value'].lower()
			for x in iclass.findall('./arch_variants/arch_variant'):
				# general and advsimd
				if 'name'    in x.attrib: attr['gen']     = x.attrib['name'].lower()
				if 'feature' in x.attrib: attr['feature'] = x.attrib['feature'].lower()

			# an instruction might have multiple forms
			asms = [canonize_asm(dump_text(x).lower()) for x in iclass.findall('./encoding/asmtemplate')]
			attr['forms'] = list(set(sum([format_form(a) for a in asms], [])))	# dedup
			attr['asm']   = asms
			attr['equiv'] = canonize_asm(dump_text(iclass.findall('./encoding/equivalent_to/asmtemplate'))).strip(' ')
			attrs.append(attr)
		return(attrs)

	def extract_opcodes(root):
		# priority: alias_mnemonic > mnemonic > id
		opcodes = filter(str.isupper, re.split(r'[\W,]+', dump_text(root.findall('./heading'))))
		opcodes = filter(lambda x: x != 'simd' and x != 'fp', [x.lower() for x in opcodes])
		return(list(set([canonize_opcode(x) for x in opcodes])))

	# extract filenames and directory for creating link
	(dir, tar, files) = prepare_expanded_tarfile(path)
	meta  = { 'path': path, 'htmldir': dir + 'xhtml/' }
	insns = dict()
	for file in files:
		content = b''.join([x for x in tar.extractfile(file).readlines()])
		root = xml.etree.ElementTree.fromstring(content.decode('UTF-8'))
		if root.tag != 'instructionsection': continue
		if 'type' in root.attrib and root.attrib['type'] == 'pseudocode': continue

		docvars = root.findall('./docvars/docvar')

		# skip_list = ['sve', 'system']			# skip sve and system instructions if needed
		skip_list = []
		if functools.reduce(lambda x, y: x or y.attrib['value'].lower() in skip_list, docvars, False): continue

		for op in extract_opcodes(root):
			if op not in insns: insns[op] = []
			insns[op].append({
				'file':  extract_filename(file).replace('.xml', '.html'),
				'attrs': parse_attributes(root),
				'brief': dump_text(root.findall('./desc/brief')),
				'desc': ' '.join([dump_text(root.findall(k)) for k in ['./desc/description', './desc/authored']]),
				'operation': dump_text(root.findall('./ps_section'), False)
			})
	return({ 'metadata': meta, 'insns': insns })




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

	def to_filepath_with_check(url, base):
		path = to_filepath(url, base)
		if not os.path.exists(path):
			error('file not found: {} (might be \'--dir\' missing or wrong)'.format(path))
			return(None)
		return(path)

	if type(urls[doc[0]]) is str:
		fnmap = {
			'description': parse_insn_xml,
			'intrinsics':  parse_intrinsics,
			'macros':      parse_macros
		}
		if doc[0] not in fnmap: return(None)
		fn   = fnmap[doc[0]]
		path = to_filepath_with_check(urls[doc[0]], base)
		return(fn(path) if path != None else None)

	if len(doc) == 1 or doc[1] not in urls[doc[0]]:
		error('second specifier needed for --doc=table, one of [\'a78\', \'a77\', \'a76\', \'n1\', \'a75\', \'a72\', \'a57\', \'a55\']')
		return(None)
	path = to_filepath_with_check(urls[doc[0]][doc[1]], base)
	return(parse_insn_table(path) if path != None else None)

def parse_all(doc_list, base = '.'):
	docs = canonize_doc_list(doc_list)
	if len(docs) == 1: return(parse_one(docs[0], base))

	def update_db(db, doc, db_ret):
		def update_dict(dic, ks, v):
			if len(ks) == 1:
				dic[ks[0]] = v
				return(dic)
			if ks[0] not in dic: dic[ks[0]] = dict()
			dic[ks[0]] = update_dict(dic[ks[0]], ks[1:], v)
			return(dic)

		for k, v in db_ret.items(): db = update_dict(db, [k] + doc, v)
		return(db)

	def update_feature_macro(insns, unused, macros):
		for insn in insns:
			if 'description' not in insns[insn]: continue
			descs = insns[insn]['description']
			for i in range(len(descs)):
				attrs = descs[i]['attrs']
				for j in range(len(attrs)):
					if 'feature' not in attrs[j]: continue
					tag = attrs[j]['feature'].split('-')[-1]
					if tag not in macros: continue
					attrs[j]['macro'] = macros[tag]
				descs[i]['attrs'] = attrs
			insns[insn]['description'] = descs
		return(insns)

	meta  = dict()
	insns = dict()
	for doc in docs:
		doc_str = '.'.join(doc)
		cmd = '{} {} parse --doc={} --dir={}'.format(sys.executable, os.path.realpath(sys.argv[0]), doc_str, base)
		message('parsing {}... (command: {})'.format(doc_str, cmd))
		ret = subprocess.run(cmd, shell = True, capture_output = True)
		db  = json.loads(ret.stdout)

		# update metadata db
		meta = update_db(meta, doc, db['metadata'])

		# update instruction db
		fn = update_db if doc[0] != 'macros' else update_feature_macro
		insns = fn(insns, doc, db['insns'])
	return({ 'metadata': meta, 'insns': insns })




# split (reorder) database
def merge_attrs(op_canon, attrs):
	def is_op_in_asm(op_canon, attrs):
		if 'asm' not in attrs: return(False)
		ops = [canonize_opcode(x.split(' ')[0]) for x in attrs['asm']]
		return(op_canon in ops)

	def merge_attrs_core(attr, a):
		for k in a:
			if k not in attr:
				attr[k] = a[k]
				continue
			if k in attr and attr[k] == a[k]: continue
			if type(attr[k]) is str:
				attr[k] += ', ' + a[k]		# string
			else:
				attr[k] += a[k]				# list
		return(attr)

	attrs_filtered = list(filter(lambda x: is_op_in_asm(op_canon, x), attrs))
	if len(attrs_filtered) > 0: attrs = attrs_filtered

	attr = attrs[0]
	for a in attrs[1:]: attr = merge_attrs_core(attr, a)
	# print(attr)
	return(attr)

def filter_descs_and_tables(op_canon, intr, descs, tables):
	def filter_descs_by_form(intr, descs):
		def revmap_core(form):
			return(form.translate(str.maketrans({ 'v': 's', 'r': 's' })))
		def revmap(attr, only_simd = True):
			if only_simd and 'advsimd-type' not in attr: return(attr['forms'])
			if only_simd and attr['advsimd-type'] == 'simd': return(attr['forms'])
			forms = [x.translate(str.maketrans({ 'v': 's', 'r': 's' })) for x in attr['forms']]
			return(forms)
		def squash(form):
			return(form.translate(str.maketrans({ 'b': 's', 'h': 's', 'w': 's', 'x': 's', 'd': 's', 'v': 's', 'r': 's' })))

		conv = str.maketrans({ 'b': 'r', 'h': 'r', 'w': 'r', 'x': 'r', 's': 'v', 'd': 'v' })
		fn1s = [
			lambda form, attr: form in attr['forms'],
			lambda form, attr: form.lower() in attr['forms'],
			lambda form, attr: form in [x.translate(conv) for x in attr['forms']],
			lambda form, attr: form.lower() in [x.translate(conv) for x in attr['forms']],
			lambda form, attr: form in revmap(attr),
			lambda form, attr: form.lower() in revmap(attr),
			lambda form, attr: form in revmap(attr, False),
			lambda form, attr: form.lower() in revmap(attr, False),
			lambda form, attr: squash(form) in revmap(attr),
			lambda form, attr: squash(form.lower()) in revmap(attr),
			lambda form, attr: squash(form) in revmap(attr, False),
			lambda form, attr: squash(form.lower()) in revmap(attr, False)
		]

		fn2s = [
			lambda fn1, intr, form, x: fn1(form, x['attr']),
			lambda fn1, intr, form, x: ('mnemonic' not in x['attr']) or (intr['op_raw'] == x['attr']['mnemonic']),
			lambda fn1, intr, form, x: ('asm'      not in x['attr']) or (intr['op_raw'] in [x.split(' ')[0] for x in x['attr']['asm']]),
			lambda fn1, intr, form, x: ('datatype' not in x['attr']) or (len(set(intr['datatypes']) & set(x['attr']['datatype'].split('-'))) > 0)
		]

		def combine_form(x):
			return([x, x[1:], x[0] + x, x[0] + x[0] + x, x[0] + x[0] + x[0] + x, x + 'wea'])

		# for debugging
		def print_descs(i, j, form, fds):
			ds = [(
				form,
				squash(form.lower()),
				x['attr']['forms'] if 'forms' in x['attr'] else '---',
				revmap(x['attr']),
				revmap(x['attr'], False),
				intr['op_raw'],
				x['attr']['mnemonic'] if 'mnemonic' in x['attr'] else '---',
				intr['datatypes'],
				x['attr']['datatype'] if 'datatype' in x['attr'] else '---',
				x['attr']['advsimd-type'] if 'advsimd-type' in x['attr'] else '---',
				[x.split(' ')[0] for x in x['attr']['asm']] if 'asm' in x['attr'] else '---') for x in fds
			]
			for d in ds: print(i, j, d)
			return

		if 'form' not in intr or len(intr['form']) == 0: return(None)
		for form in combine_form(intr['form']):
			for i, fn1 in enumerate(fn1s):
				filtered_descs = sum([[{ 'desc': d, 'attr': a } for a in d['attrs']] for d in descs], [])
				# print_descs(i, 0, form, filtered_descs)
				for j, fn2 in enumerate(fn2s):
					filtered_descs = list(filter(lambda x: fn2(fn1, intr, form, x), filtered_descs))
					# print_descs(i, j + 1, form, filtered_descs)
					if len(filtered_descs) == 0: break
					if len(filtered_descs) == 1: return(filtered_descs[0])
		return(None)

		# for debugging
		print('failed filtering')
		for d in descs:
			for a in d['attrs']:
				print(a['asm'], intr['form'].lower(), a['forms'], a['advsimd-type'] if 'advsimd-type' in a else '---', squash(intr['form']), [x.translate(conv) for x in a['forms']], revmap(a), revmap(a, True))
		return(None)

	def filter_tables_by_form(attr, tables):
		if 'instr-class' not in attr: return(tables)
		canon_class = { 'advsimd': 'asimd', 'fpsimd': 'asimd', 'float': 'float', 'general': 'general', 'system': 'system' }
		# print(attr, table)
		iclass = canon_class[attr['instr-class']]
		return(list(filter(lambda x: x['iclass'] == iclass, tables)))

	# check form available in intrinsics, impossible to filter descriptions if none
	if 'form' not in intr: return([({ 'desc': d, 'attr': merge_attrs(op_canon, d['attrs']) }, tables) for d in descs])

	# first try filtering descriptions by form
	filtered_descs = filter_descs_by_form(intr, descs)
	if filtered_descs == None: return(None)

	# gather latency table that are related to the class; table is dict, table[processor] is list
	filtered_table = dict([(proc, filter_tables_by_form(filtered_descs['attr'], tables[proc])) for proc in tables])
	return([(filtered_descs, filtered_table)])

def split_insns(filename):
	def find_or(d, k, o = ''):
		return(d[k] if k in d else o)

	def copy_as(dst, dkey, src, skey):
		if skey not in src: return(dst)
		dst[dkey] = src[skey]
		return(dst)

	def compose_brief(op_canon, intr, desc):
		brief = {
			'ic': find_or(desc['attr'], 'instr-class'),
			'ft': find_or(desc['attr'], 'feature'),
			'op': find_or(intr, 'op_raw', op_canon),
			'it': find_or(intr, 'intrinsics')
		}
		brief = copy_as(brief, 'ip', intr, 'page')
		brief = copy_as(brief, 'mc', desc['attr'], 'macro')
		brief = copy_as(brief, 'as', desc['attr'], 'asm')
		brief = copy_as(brief, 'eq', desc['attr'], 'equiv')
		brief = copy_as(brief, 'cs', desc['attr'], 'cond-setting')
		brief = copy_as(brief, 'rf', desc['desc'], 'file')
		return(brief)

	def compose_description(op_canon, intr, desc):
		description = {
			'bf': find_or(desc['desc'], 'brief'),
			'dt': find_or(desc['desc'], 'desc'),
			'or': find_or(desc['desc'], 'operation')
		}
		return(description)

	def compose_tables(ts):
		def compose_table(t, com):
			table = {
				# 'op': find_or(t, 'op_raw'),
				'vr': list(filter(lambda x: x not in com, find_or(t, 'variant', []))),
				'lt': find_or(t, 'latency'),
				'tp': find_or(t, 'throughput'),
				'ip': find_or(t, 'pipes'),
				'pp': find_or(t, 'page'),
			}
			return(table)

		if len(ts) == 0: return(ts)
		all    = set(sum([x['variant'] for x in sum([v for v in ts.values()], [])], []))
		common = functools.reduce(lambda x, y: x & set(y['variant']), sum([v for v in ts.values()], []), all)

		tables = dict()
		for k, ts in ts.items(): tables[k] = [compose_table(t, common) for t in ts]
		return(tables)

	def compose_blank(op_canon, intr):
		# print('blank', op_canon)
		# print(intr)
		brief = {
			'ic': 'advsimd' if op_canon in ['zip', 'uzp', 'trn', 'cmla', 'combine', 'dup'] else 'unknown',
			'ft': '',
			'op': find_or(intr, 'op_raw', op_canon),
			'it': find_or(intr, 'intrinsics'),
		}
		brief = copy_as(brief, 'ip', intr, 'page')
		brief = copy_as(brief, 'as', intr, 'sequence')
		return({
			'bf': brief,
			'ds': { 'bf': '', 'dt': '', 'or': '' },
			'tb': []
		})

	def split_insns_intl(op_canon, v):
		if op_canon == '': return([])

		tables = v['table'] if 'table' in v else dict()
		intrs  = v['intrinsics'] if 'intrinsics' in v else [dict()]

		if 'description' not in v: return([compose_blank(op_canon, i) for i in intrs])

		# for each instruction class
		descs = v['description']
		for i in range(len(descs)): descs[i]['index'] = i

		insns = []
		for intr in intrs:
			# print(op_canon, intr)
			xs = filter_descs_and_tables(op_canon, intr, descs, tables)
			if xs == None: 
				insns.append(compose_blank(op_canon, intr))
				continue
			# print('desc: ', d)
			# print('table: ', t)
			insns.extend([{
				'bf': compose_brief(op_canon, intr, d),
				'ds': compose_description(op_canon, intr, d),
				'tb': compose_tables(ts),
				'index': d['desc']['index']
			} for d, ts in xs])

		# print(insns)
		covered = set([x['index'] for x in insns if 'index' in x])
		for i in range(len(descs)):
			if i in covered: continue
			d = {
				'attr': merge_attrs(op_canon, descs[i]['attrs']),
				'desc': descs[i]
			}
			insns.append({
				'bf': compose_brief(op_canon, {}, d),
				'ds': compose_description(op_canon, {}, d),
				'tb': [],
				'index': i
			})
		for insn in insns: insn.pop('index', None)
		return(insns)

	# read json file
	meta  = dict()
	insns = []
	with open(filename) as f:
		db = json.load(f)
		meta = db['metadata']
		for op, v in db['insns'].items(): insns.extend(split_insns_intl(op, v))
	insns.sort(key = lambda x: x['bf']['op'] if 'bf' in x else '')
	return({ 'metadata': meta, 'insns': insns })




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
		help    = 'list of documents to fetch, one or more of [\'intrinsics\', \'table\', \'description\'], or \'all\' for everything',
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
		help    = 'list of documents to fetch, one or more of [\'intrinsics\', \'table\', \'description\'], or \'all\' for everything',
		default = []
	)

	pa = sub.add_parser('split')
	pa.set_defaults(func = split_insns)
	pa.add_argument('--db',
		action  = 'store',
		help    = 'json object generated by \'parse.py parse --doc=all\'',
		default = ''
	)

	args = ap.parse_args()
	if args.func == split_insns:
		ret = args.func(args.db)
		print(json.dumps(ret))
		exit()

	if args.doc == [] or args.doc[0] == 'all': args.doc = build_doc_list()
	if not os.path.exists(args.dir): os.makedirs(args.dir)

	ret = args.func(args.doc, args.dir)
	if ret != None: print(json.dumps(ret))

	# fetch_all()
	# insns = parse_all()
	# insns = parse_insn_table(to_filepath(urls['table']['a55'], '.'))
	# insns = parse_intrinsics(to_filepath(urls['intrinsics'], '.'))



