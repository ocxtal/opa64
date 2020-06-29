

var _windowHeight;
var _metadata;
var _original;
var _filtered;


function highlightIntl(cls, intr_str) {
  var s = $("<div>").addClass(cls);
  if(intr_str.length == 0) { return(s); }

  var parts  = intr_str.split(/[(),]+/).filter(function (x) { return(x != ""); });
  var delims = Array(parts.length).fill(', ');
  delims[0]  = '(';
  delims[parts.length - 1] = ');';
  parts.forEach(function (x, i) {
    y = parts[i].trim().split(' ');
    s.append($("<span>").addClass("opv86-code-type").text(y[0] + ' '));
    s.append($("<span>").addClass("opv86-code-base").text(y[1] + delims[i]));
  });
  return(s);
}

function createIntrLink(cls, txt) {
  var s = $("<div>").addClass(cls);
  var pdfpath = _metadata.path.intrinsics + "#page=" + txt;
  var fulltxt = "Intrinsics Guide p." + txt;
  return(s.append($(`<a target="_blank" href='${pdfpath}'>${fulltxt}</a>`)));
}

function createInsnLink(cls, txt) {
  var s = $("<div>").addClass(cls);
  var htmlpath = _metadata.htmldir.description + txt;
  return(s.append($(`<a target="_blank" href='${htmlpath}'>${txt}</a>`)));
}

function createText(cls, txt) {
  return($("<div>").addClass(cls).text(txt));
}

function extractText(op, tag) {
  var txt = op.bf[tag];
  return(Array.isArray(txt) ? txt : [txt]);
}

function createSynopsisText(op, tag, key) {
  var tagToClass = {
    "op": "opv86-synopsis-label",
    "it": "opv86-synopsis-label",
    "as": "opv86-synopsis-label",
    "mc": "opv86-synopsis-label",
    "eq": "opv86-synopsis-label"
  };
  var cls = tag in tagToClass ? tagToClass[tag] : "opv86-synopsis-text";

  var tagToFn = {
    "it": highlightIntl,
    "ip": createIntrLink,
    "rf": createInsnLink
  };
  var fn = tag in tagToFn ? tagToFn[tag] : createText;

  var c = $("<div>").addClass("opv86-synopsis");
  var arr = extractText(op, tag);
  arr.forEach(function (x, i) {
    var t = $("<div>").addClass("opv86-synopsis-tag");
    if(i == 0) { t.text(key); }
    c.append(t).append(fn(tagToClass[tag], x));
  });
  return(c);
}

function createSynopsis(op) {
  var h = $("<div>").addClass("opv86-details-section").text("Synopsis");
  var b = $("<div>").addClass("opv86-details-body");

  var tagToKeyName = {
    "ic": "Instruction Class",
    "ft": "Feature",
    "op": "Opcode",
    "it": "Intrinsics",
    "as": "Assemblies",
    "mc": "Feature Macro",
    "eq": "Equivalent to",
    "cs": "Condition Setting",
    "rf": "References",
    "ip": "References"
  };

  Object.keys(tagToKeyName).forEach(function (x) {
    if(x in op.bf && op.bf[x] != "") {
      var key = tagToKeyName[x];
      if(x == "ip" && "rf" in op.bf) { key = ""; }
      b.append(createSynopsisText(op, x, key));
    }
  });
  return(h.append(b));
}

function createDescription(op) {
  if(op.ds.dt.length == 0) { return(undefined); }
  var s = $("<div>").addClass("opv86-details-section").text("Description");
  s.append($("<div>").addClass("opv86-details-body").text(op.ds.dt));
  return(s);
}

function createOperation(op) {
  if(op.ds.or.length == 0) { return(undefined); }
  var s = $("<div>").addClass("opv86-details-section").text("Operation");
  var c = $("<div>").addClass("opv86-details-body");
  var t = $("<div>").addClass("opv86-table-container");
  t.append($("<div>").addClass("opv86-details-pseudocode").text(op.ds.or));
  c.append(t);
  s.append(c);
  return(s);
}

function getFullArchName(arch) {
  if(arch.startsWith("a")) { return("Cortex-" + arch.toUpperCase()); }
  if(arch.startsWith("n")) { return("Neoverse-" + arch.toUpperCase()); }
  return(arch);
}

function createTableReference(arch, page) {
  var pdfpath = _metadata.path.table[arch];
  return($("<div>").addClass("opv86-table-text").append($(`<a target="_blank" href='${pdfpath}#page=${page}'>p.${page}</a>`)));
}

function createTableHeader() {
  var h = $("<div>").addClass("opv86-table-header");
  h.append($("<div>").addClass("opv86-header-text").text("uArch"));
  h.append($("<div>").addClass("opv86-header-text").text("Variant / Form"));
  h.append($("<div>").addClass("opv86-header-text").text("Latency"));
  h.append($("<div>").addClass("opv86-header-text").text("Throughput"));
  h.append($("<div>").addClass("opv86-header-text").text("Pipes"));
  h.append($("<div>").addClass("opv86-header-text").text("References"));
  return(h);
}

function createTableRow(arch, row) {
  var s = $("<div>").addClass("opv86-table-variant");
  s.append($("<div>").addClass("opv86-table-text").text(row.vr));
  s.append($("<div>").addClass("opv86-table-text").text(row.lt));
  s.append($("<div>").addClass("opv86-table-text").text(row.tp));
  s.append($("<div>").addClass("opv86-table-text").text(row.ip));
  s.append(createTableReference(arch, row.pp));
  return(s);
}

function createTableIntl(op) {
  var table = $("<div>");
  table.append(createTableHeader());

  for(var arch in op.tb) {
    var label = $("<div>").addClass("opv86-table-text").text(getFullArchName(arch));
    var variants = $("<div>").addClass("opv86-table-variant-container");
    op.tb[arch].forEach(function (r) { variants.append(createTableRow(arch, r)); });
    table.append($("<div>").addClass("opv86-table-arch").append(label).append(variants));
  }
  return(table);
}

function createTable(op) {
  if(Object.keys(op.tb).length == 0) { return(undefined); }
  var t = $("<div>").addClass("opv86-details-section").text("Latency & Throughput");
  t.append($("<div>").addClass("opv86-details-body").addClass("opv86-table-container").append(createTableIntl(op)));
  return(t);
}

function createDetails(op, id) {
  var g = $("<div>").addClass("opv86-details-container");
  var s = createSynopsis(op);
  var d = createDescription(op);
  var o = createOperation(op);
  var t = createTable(op);

  g.append(s);
  if(d !== undefined) { g.append(d); }
  if(d !== undefined) { g.append(o); }
  if(d !== undefined) { g.append(t); }
  return(g);
}

function createHeader() {
  var h = $("<div>").addClass("opv86-oplist-header");
  h.append($("<div>").addClass("opv86-header-text").text("Class"));
  h.append($("<div>").addClass("opv86-header-text").text("Feature"));
  h.append($("<div>").addClass("opv86-header-text"));
  h.append($("<div>").addClass("opv86-header-text").text("Opcode"));
  h.append($("<div>").addClass("opv86-header-text"));
  h.append($("<div>").addClass("opv86-header-text").text("Intrinsics"));
  h.append($("<div>").addClass("opv86-header-text"));
  h.append($("<div>").addClass("opv86-header-text").text("Description"));
  return(h);
}

function setupOnClick(s) {
  s.click(function(e) {
    var p = $(this).parent();
    var d = p.find(".opv86-details-container");
    if(d.length == 0) {
      var id = $(this)[0].id;
      var op = _filtered[id];
      d = createDetails(op, id);
      p.append(d);
    }
    if(d.css("display") == "none") {
      d.slideDown(200);
    } else {
      d.slideUp(200);
    }
  });
  return(s);
}

function findBackgroundColor(op) {
  var iclass  = op.bf.ic;
  var feature = op.bf.ft;
  if(feature.startsWith("armv8.1")) { return("#ffd1c2"); }
  if(feature.startsWith("armv8.2")) { return("#ffc2c2"); }
  if(feature.startsWith("armv8.3")) { return("#ffc2e0"); }
  if(feature.startsWith("armv8.4")) { return("#ffc2ff"); }
  if(feature.startsWith("armv8.5")) { return("#e0c2ff"); }
  if(feature.startsWith("armv8.6")) { return("#c2c2ff"); }

  if(iclass == "general") { return("#ffffc2"); }
  if(iclass == "advsimd") { return("#ffeec0"); }
  if(iclass == "float") { return("#e0ffc2"); }
  if(iclass == "fpsimd") { return("#c2ffc2"); }
  if(iclass == "sve") { return("#c2f0ff"); }
  return("#cccccc");
}

function createBrief(op, id) {
  var c = { "background-color": findBackgroundColor(op) };
  var s = $("<div>").addClass("opv86-brief-grid").attr({ "id": id });

  s.append($("<div>").addClass("opv86-brief-text").text(op.bf.ic).css(c));
  s.append($("<div>").addClass("opv86-brief-text").text(op.bf.ft).css(c));
  s.append($("<div>").addClass("opv86-brief-text"));
  s.append($("<div>").addClass("opv86-brief-label").text(op.bf.op));
  s.append($("<div>").addClass("opv86-brief-text"));
  s.append(highlightIntl("opv86-brief-label", op.bf.it));
  s.append($("<div>").addClass("opv86-brief-text"));
  s.append($("<div>").addClass("opv86-brief-text").text(op.ds.bf));
  return(setupOnClick(s));
}


function extendOplist(oplist, data, from, to) {
  if(to > data.length) { to = data.length; }
  for(var i = from; i < to; i++) {
    var op = data[i];
    var s = createBrief(op, i);
    var c = $("<div>").addClass("opv86-op-container").append(s);
    oplist.append(c);
  }
}

function updateHeight () {
  _windowHeight = $(window).height();
}

function extendOnScroll() {
  if($(window).scrollTop() > ($(document).height() - 2 * _windowHeight)) {
    var oplist = $("#oplist");
    var data = _filtered;
    var start = oplist[0].childNodes.length;
    extendOplist(oplist, data, start, start + 50);
  }
}

function filterClass(op, cls) {
  if(cls.includes("intrinsics-only") && op.bf.it == "") { return(false); }
  if(cls.includes("general-only") && op.bf.ic != "general") { return(false); }
  if(!cls.includes("include-sve") && op.bf.ic == "sve") { return(false); }
  if(!cls.includes("include-system") && op.bf.ic == "system") { return(false); }
  return(true);
}

function findKey(op, filter_word) {
  var keys = ["ic", "ft", "op", "it"];
  for(var k of keys) { if(op.bf[k].indexOf(filter_word) != -1) { return(true); } }

  var keys_opt = ["as"];
  for(var k of keys_opt) { if(k in op.bf && op.bf[k].indexOf(filter_word) != -1) { return(true); } }

  if(op.ds.bf.toLowerCase().indexOf(filter_word) != -1) { return(true); }
  if(op.ds.dt.toLowerCase().indexOf(filter_word) != -1) { return(true); }
  return(false);
}

function rebuildOplist() {
  var oplist = $("#oplist");
  oplist.empty();
  oplist.append(createHeader());

  var clskeys = ["intrinsics-only", "general-only", "include-sve", "include-system"];
  var filter_cls = clskeys.filter(function (x) { return($("#" + x).is(':checked')); });
  var filter_key = $("#filter-value").val().toLowerCase();

  _filtered = _original.filter(function (x) { return(filterClass(x, filter_cls) && findKey(x, filter_key)); })

  var num_recs = ($(window).height() / 30) * 5;
  extendOplist(oplist, _filtered, 0, num_recs);
}

function initOplist(data) {
  $("#filter-value").val("");
  _metadata = data.metadata;
  _original = data.insns;
  _windowHeight = $(window).height();
  rebuildOplist();
}

$.getJSON(`./data/db.json`, function(data) {
  initOplist(data);

  $("#filter-checkbox").change(function () { rebuildOplist(); });
  $("#filter-value").keyup(function () { rebuildOplist(); });
  $(window).resize(updateHeight);
  $(window).scroll(extendOnScroll);
});




