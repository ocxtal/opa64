


var _windowHeight;
var _original;
var _filtered;


function createSynopsisText(tag, text) {
  var tagToClass = {
    "Opcode": "opv86-synopsis-label",
    "Intrinsics": "opv86-synopsis-label",
    "Assembly": "opv86-synopsis-label",
    "Equivalent to": "opv86-synopsis-label"
  };
  var cls = tag in tagToClass ? tagToClass[tag] : "opv86-synopsis-text";

  var c = $("<div>").addClass("opv86-synopsis");
  var arr = Array.isArray(text) ? text : [text];
  for(var i in arr.length) {
    c.append($("<div>").addClass("opv86-synopsis-tag").text(i == 0 ? tag : ""));
    c.append($("<div>").addClass(tagToClass[tag]).text(arr[i]));
  }

  c.append($("<div>").addClass("opv86-synopsis-tag").text(tag));
  if(tag in tagToClass) {
    c.append($("<div>").addClass(tagToClass[tag]).text(text));
  } else {
    c.append($("<div>").addClass().text(text));
  }
  return(c);
}

function createSynopsisLabel(tag, text) {
  var c = $("<div>").addClass("opv86-synopsis");
  c.append($("<div>").addClass("opv86-synopsis-tag").text(tag));
  c.append($("<div>").addClass("opv86-synopsis-label").text(text));
  return(c);
}

function createSynopsis(op) {
  var h = $("<div>").addClass("opv86-details-section").text("Synopsis");
  var b = $("<div>").addClass("opv86-details-body");
  Object.keys(op.brief).forEach(function (x) {
    if(op.brief[x] != "") { b.append(createSynopsisText(x, op.brief[x])); }
  });
  return(h.append(b));
}

function createDescription(op) {
  if(op.description.detailed.length == 0) { return(undefined); }
  var s = $("<div>").addClass("opv86-details-section").text("Description");
  s.append($("<div>").addClass("opv86-details-body").text(op.description.detailed));
  return(s);
}

function createOperation(op) {
  if(op.description.operation.length == 0) { return(undefined); }
  var s = $("<div>").addClass("opv86-details-section").text("Operation");
  var c = $("<div>").addClass("opv86-table-container");
  c.append($("<div>").addClass("opv86-details-pseudocode").text(op.description.operation));
  s.append(c);
  return(s);
}

function getFullArchName(arch) {
  if(arch.startsWith("a")) { return("Cortex-" + arch.toUpperCase()); }
  if(arch.startsWith("n")) { return("Neoverse-" + arch.toUpperCase()); }
  return(arch);
}

function canonizeNotes(notes) {
  if(notes == "-") { return(""); }
  return(notes);
}

function createTableHeader() {
  var h = $("<div>").addClass("opv86-table-header");
  h.append($("<div>").addClass("opv86-header-text").text("uArch"));
  h.append($("<div>").addClass("opv86-header-text").text("Variant / Form"));
  h.append($("<div>").addClass("opv86-header-text").text("Latency"));
  h.append($("<div>").addClass("opv86-header-text").text("Throughput"));
  h.append($("<div>").addClass("opv86-header-text").text("Pipes"));
  h.append($("<div>").addClass("opv86-header-text").text("Notes"));
  return(h);
}

function createTableRow(row) {
  var s = $("<div>").addClass("opv86-table-variant");
  s.append($("<div>").addClass("opv86-table-text").text(row.variant));
  s.append($("<div>").addClass("opv86-table-text").text(row.latency));
  s.append($("<div>").addClass("opv86-table-text").text(row.throughput));
  s.append($("<div>").addClass("opv86-table-text").text(row.pipes));
  s.append($("<div>").addClass("opv86-table-text").text(canonizeNotes(row.notes)));
  return(s);
}

function createTableIntl(op) {
  var table = $("<div>");
  table.append(createTableHeader());

  for(var arch in op.table) {
    var label = $("<div>").addClass("opv86-table-text").text(getFullArchName(arch));
    var variants = $("<div>").addClass("opv86-table-variant-container");
    op.table[arch].forEach(function (r) { variants.append(createTableRow(r)); });
    table.append($("<div>").addClass("opv86-table-arch").append(label).append(variants));
  }
  return(table);
}

function createTable(op) {
  if(Object.keys(op.table).length == 0) { return(undefined); }
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
  var iclass  = op.brief['Instruction Class'];
  var feature = op.brief['Feature'];
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
  return("#cccccc");
}

function createBrief(op, id) {
  var c = { "background-color": findBackgroundColor(op) };
  var s = $("<div>").addClass("opv86-brief-grid").attr({ "id": id });
  s.append($("<div>").addClass("opv86-brief-text").text(op.brief['Instruction Class']).css(c));
  s.append($("<div>").addClass("opv86-brief-text").text(op.brief['Feature']).css(c));
  s.append($("<div>").addClass("opv86-brief-text"));
  s.append($("<div>").addClass("opv86-brief-label").text(op.brief['Opcode']));
  s.append($("<div>").addClass("opv86-brief-text"));
  s.append($("<div>").addClass("opv86-brief-label").text(op.brief['Intrinsics']));
  s.append($("<div>").addClass("opv86-brief-text"));
  s.append($("<div>").addClass("opv86-brief-text").text(op.description.brief));
  return(setupOnClick(s));
}


function extendTable(oplist, data, from, to) {
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
    extendTable(oplist, data, start, start + 20);
  }
}

function rebuildTable(data) {
  var oplist = $("#oplist");
  oplist.empty();
  oplist.append(createHeader());

  var count = ($(window).height() / 30) * 5;
  extendTable(oplist, data, 0, count);
}

function findKey(op, filter_word) {
  var keys = ["Instruction Class", "Feature", "Opcode", "Intrinsics", "Assembly"];
  for(var k of keys) {
    // console.log(op.brief[k]);
    if(op.brief[k].indexOf(filter_word) != -1) { return(true); }
  }
  // if(is_brief_matched) { return(true); }
  if(op.description.brief.toLowerCase().indexOf(filter_word) != -1) { return(true); }
  if(op.description.detailed.toLowerCase().indexOf(filter_word) != -1) { return(true); }
  // console.log(filter_word, op);
  return(false);
}

function rebuild(filter) {
  var filter_word = filter.toLowerCase();
  _filtered = _original.filter(function (x) { return(findKey(x, filter_word)); });
  rebuildTable(_filtered);
  // console.log(_filtered);
}

function init(data) {
  document.getElementById("filter-value").value = "";
  _original = data;
  _filtered = data.slice();
  _windowHeight = $(window).height();
  rebuildTable(_filtered);
}

// $.getJSON(`truncated.json` , function(data) {
$.getJSON(`./data/db.json` , function(data) {
  init(data);
  document.getElementById("filter-value").addEventListener("keyup", function () {
    rebuild(document.getElementById("filter-value").value);
  });
  $(window).resize(updateHeight);
  $(window).scroll(extendOnScroll);
});




