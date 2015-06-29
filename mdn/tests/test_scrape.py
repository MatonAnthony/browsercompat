# coding: utf-8
"""Test mdn.scrape."""
from __future__ import unicode_literals
from datetime import date
from json import dumps

from mdn.models import FeaturePage
from mdn.scrape import (
    date_to_iso, end_of_line, page_grammar, scrape_page, scrape_feature_page,
    PageVisitor, ScrapedViewFeature)
from webplatformcompat.models import (
    Browser, Feature, Section, Specification, Support, Version)
from .base import TestCase


class TestGrammar(TestCase):
    def assert_other_h2(self, other_h2, expected_title):
        """Assert the title is extracted by rule other_h2"""
        parsed = page_grammar['other_h2'].parse(other_h2)
        capture = parsed.children[6]
        self.assertEqual(expected_title, capture.text)

    def test_other_h2_plain(self):
        other_h2 = "<h2 id=\"Summary\">Summary</h2>"
        expected_title = "Summary"
        self.assert_other_h2(other_h2, expected_title)

    def test_other_h2_code(self):
        other_h2 = "<h2 id=\"Summary\"><code>Summary</code></h2>"
        expected_title = "<code>Summary</code>"
        self.assert_other_h2(other_h2, expected_title)

    def assert_spec_h2(self, spec_h2, expected_attrs, expected_title):
        parsed = page_grammar['spec_h2'].parse(spec_h2)
        attrs = parsed.children[2]
        title = parsed.children[6]
        self.assertEqual(expected_attrs, attrs.text)
        self.assertEqual(expected_title, title.text)

    def test_spec_h2_expected(self):
        spec_h2 = '<h2 id="Specifications">Specifications</h2>'
        expected_attrs = 'id="Specifications"'
        expected_title = 'Specifications'
        self.assert_spec_h2(spec_h2, expected_attrs, expected_title)

    def test_spec_h2_browser_compat(self):
        spec_h2 = (
            '<h2 id="Browser_compatibility" name="Browser_compatibility">'
            'Specifications</h2>')
        expected_attrs = (
            'id="Browser_compatibility" name="Browser_compatibility"')
        expected_title = "Specifications"
        self.assert_spec_h2(spec_h2, expected_attrs, expected_title)

    def assert_whynospec(self, text):
        parsed = page_grammar['whynospec'].parse(text)
        assert parsed

    def test_whynospec_plain(self):
        text = "<p>{{WhyNoSpecStart}}There is no spec{{WhyNoSpecEnd}}</p>"
        self.assert_whynospec(text)

    def test_whynospec_spaces(self):
        text = """\
<p>
   {{ WhyNoSpecStart }} There is no spec {{ WhyNoSpecEnd }}
</p>"""
        self.assert_whynospec(text)

    def test_whynospec_inner_kuma(self):
        text = """\
<p>
{{WhyNoSpecStart}}
Not part of any current spec, but it was in early drafts of
{{SpecName("CSS3 Animations")}}.
{{WhyNoSpecEnd}}
</p>"""
        self.assert_whynospec(text)

    def assert_spec_headers(self, spec_headers, expected_tag, expected_title):
        parsed = page_grammar['spec_headers'].parse(spec_headers)
        th_elems = parsed.children[2]
        col1 = th_elems.children[0]
        tag = col1.children[0]
        title = col1.children[2]
        self.assertEqual(expected_tag, tag.text)
        self.assertEqual(expected_title, title.text)

    def test_spec_headers_scoped(self):
        # Most common version
        spec_headers = """<tr>
          <th scope="col">Specification</th>
          <th scope="col">Status</th>
          <th scope="col">Comment</th>
        </tr>"""
        expected_tag = '<th scope="col">'
        expected_title = 'Specification'
        self.assert_spec_headers(spec_headers, expected_tag, expected_title)

    def test_spec_headers_unscoped(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/inherit
        spec_headers = """<tr>
          <th>Specification</th>
          <th>Status</th>
          <th>Comment</th>
        </tr>"""
        expected_tag = '<th>'
        expected_title = 'Specification'
        self.assert_spec_headers(spec_headers, expected_tag, expected_title)

    def test_spec_headers_strong(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage
        spec_headers = """<tr>
          <th scope="col"><strong>Specification</strong></th>
          <th scope="col"><strong>Status</strong></th>
          <th scope="col"><strong>Comment</strong></th>
        </tr>"""
        expected_tag = '<th scope="col">'
        expected_title = '<strong>Specification</strong>'
        self.assert_spec_headers(spec_headers, expected_tag, expected_title)

    def assert_spec_row(self, spec_row, expected_tag):
        parsed = page_grammar['spec_row'].parse(spec_row)
        tr = parsed.children[0]
        self.assertEqual(expected_tag, tr.text)

    def test_spec_row_standard(self):
        spec_row = """<tr>
          <td>{{SpecName('CSS3 Backgrounds', '#the-background-size',
            'background-size')}}</td>
          <td>{{Spec2('CSS3 Backgrounds')}}</td>
          <td></td>
        </tr>"""
        expected_tag = '<tr>'
        self.assert_spec_row(spec_row, expected_tag)

    def test_spec_row_styled(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/inherit
        spec_row = """<tr style="vertical-align: top;">
          <td>{{ SpecName('CSS2.1', "cascade.html#value-def-inherit",
            "inherit") }}</td>
          <td>{{ Spec2('CSS2.1') }}</td>
          <td>Initial definition</td>
        </tr>"""
        expected_tag = '<tr style="vertical-align: top;">'
        self.assert_spec_row(spec_row, expected_tag)

    def assert_specname_td(self, specname_td, expected_tag, expected_text):
        parsed = page_grammar['specname_td'].parse(specname_td)
        tr = parsed.children[0]
        specname_text = parsed.children[2]
        self.assertEqual(expected_tag, tr.text)
        self.assertEqual(expected_text, specname_text.text)

    def test_specname_td_standard(self):
        specname_td = (
            "<td>{{SpecName('CSS3 Backgrounds', '#the-background-size',"
            " 'background-size')}}</td>")
        expected_tag = '<td>'
        expected_text = (
            "{{SpecName('CSS3 Backgrounds', '#the-background-size',"
            " 'background-size')}}")
        self.assert_specname_td(specname_td, expected_tag, expected_text)

    def test_specname_td_styled(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/inherit
        specname_td = (
            "<td style=\"vertical-align: top;\">{{ SpecName('CSS2.1',"
            " \"cascade.html#value-def-inherit\", \"inherit\") }}</td>")
        expected_tag = '<td style="vertical-align: top;">'
        expected_text = (
            "{{ SpecName('CSS2.1', \"cascade.html#value-def-inherit\","
            " \"inherit\") }}")
        self.assert_specname_td(specname_td, expected_tag, expected_text)

    def test_specname_td_ES1_legacy(self):
        # /en-US/docs/Web/JavaScript/Reference/Operators/this
        specname_td = "<td>ECMAScript 1st Edition.</td>"
        expected_tag = '<td>'
        expected_text = "ECMAScript 1st Edition."
        self.assert_specname_td(specname_td, expected_tag, expected_text)

    def assert_spec2_td(self, spec2_td, expected_tag, expected_text):
        parsed = page_grammar['spec2_td'].parse(spec2_td)
        tr = parsed.children[0]
        spec2_text = parsed.children[2]
        self.assertEqual(expected_tag, tr.text)
        self.assertEqual(expected_text, spec2_text.text)

    def test_spec2_td_standard(self):
        spec2_td = "<td>{{Spec2('CSS3 Backgrounds')}}</td>"
        expected_tag = '<td>'
        expected_text = "{{Spec2('CSS3 Backgrounds')}}"
        self.assert_spec2_td(spec2_td, expected_tag, expected_text)

    def test_spec2_td_styled(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/inherit
        spec2_td = """<td style="vertical-align: top;">
            {{ Spec2("CSS2.1") }}
        </td>"""
        expected_tag = '<td style="vertical-align: top;">'
        expected_text = '{{ Spec2("CSS2.1") }}\n        '
        self.assert_spec2_td(spec2_td, expected_tag, expected_text)

    def test_spec2_td_text(self):
        # /en-US/docs/Web/JavaScript/Reference/Operators/this
        spec2_td = "<td>Standard</td>"
        expected_tag = '<td>'
        expected_text = 'Standard'
        self.assert_spec2_td(spec2_td, expected_tag, expected_text)

    def assert_specdesc_td(self, specdesc_td, expected_tag, expected_desc):
        parsed = page_grammar['specdesc_td'].parse(specdesc_td)
        tag = parsed.children[0]
        self.assertEqual(expected_tag, tag.text)
        capture = parsed.children[2]
        self.assertEqual(expected_desc, capture.text)

    def test_specdesc_td_empty(self):
        specdesc_td = '<td></td>'
        expected_tag = '<td>'
        expected_desc = ''
        self.assert_specdesc_td(specdesc_td, expected_tag, expected_desc)

    def test_specdesc_td_plain_text(self):
        specdesc_td = '<td>Plain Text</td>'
        expected_tag = '<td>'
        expected_desc = 'Plain Text'
        self.assert_specdesc_td(specdesc_td, expected_tag, expected_desc)

    def test_specdesc_td_html(self):
        specdesc_td = "<td>Defines <code>right</code> as animatable.</td>"
        expected_tag = '<td>'
        expected_desc = 'Defines <code>right</code> as animatable.'
        self.assert_specdesc_td(specdesc_td, expected_tag, expected_desc)

    def test_specdesc_td_styled(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/inherit
        specdesc_td = """<td style=\"vertical-align: top;\">
            Initial definition.
        </td>"""
        expected_tag = '<td style="vertical-align: top;">'
        expected_desc = "Initial definition.\n        "
        self.assert_specdesc_td(specdesc_td, expected_tag, expected_desc)

    def assert_compat_headers(
            self, headers, expected_feature, expected_browsers):
        parsed = page_grammar['compat_headers'].parse(headers)
        feature = parsed.children[2]
        browsers = parsed.children[4]
        self.assertEqual(expected_feature, feature.text)
        self.assertEqual(expected_browsers, browsers.text)

    def test_compat_headers_standard(self):
        headers = "<tr><th>Feature</th><th>Firefox</th></tr>"
        expected_feature = '<th>Feature</th>'
        expected_browsers = '<th>Firefox</th>'
        self.assert_compat_headers(
            headers, expected_feature, expected_browsers)

    def test_compat_headers_strong(self):
        headers = (
            "<tr><th><strong>Feature</strong></th>"
            "<th><strong>Firefox</strong></th></tr>")
        expected_feature = '<th><strong>Feature</strong></th>'
        expected_browsers = '<th><strong>Firefox</strong></th>'
        self.assert_compat_headers(
            headers, expected_feature, expected_browsers)

    def test_compat_footnotes(self):
        footnotes = '<p>[2] A footnote</p>'
        parsed = page_grammar['compat_footnotes'].parse(footnotes)
        self.assertEqual(footnotes, parsed.text)

    def assert_cell_version(self, text, version, eng_version=None):
        match = page_grammar['cell_version'].parse(text).match.groupdict()
        expected = {'version': version, 'eng_version': eng_version}
        self.assertEqual(expected, match)

    def test_cell_version_number(self):
        self.assert_cell_version("1", version="1")

    def test_cell_version_number_dotted(self):
        self.assert_cell_version("1.0", version="1.0")

    def test_cell_version_number_spaces(self):
        self.assert_cell_version("1 ", version="1")

    def test_cell_version_number_dotted_spaces(self):
        self.assert_cell_version("1.0\n\t", version="1.0")

    def test_cell_version_number_with_engine(self):
        self.assert_cell_version("1.0 (85)", version="1.0", eng_version="85")

    def test_cell_version_number_with_dotted_engine(self):
        self.assert_cell_version(
            "5.0 (532.5)", version="5.0", eng_version="532.5")

    def assert_cell_no_prefix(self, text):
        node = page_grammar['cell_noprefix'].parse(text)
        self.assertEqual(text, node.text)

    def test_unprefixed(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/AudioContext.createBufferSource
        self.assert_cell_no_prefix(' (unprefixed) ')

    def test_noprefix(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/Navigator.vibrate
        self.assert_cell_no_prefix(' (no prefix) ')

    def test_without_prefix_naked(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/text-decoration-line
        self.assert_cell_no_prefix('without prefix')

    def test_without_prefix(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/BatteryManager
        self.assert_cell_no_prefix('(without prefix)')

    def assert_cell_partial(self, text):
        node = page_grammar['cell_partial'].parse(text)
        self.assertEqual(text, node.text)

    def test_comma_partial(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/IDBCursor
        self.assert_cell_partial(', partial')

    def test_parens_partal(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/text-decoration
        self.assert_cell_partial('(partial)')


sample_spec_row = """\
<tr>
   <td>{{SpecName('CSS3 Backgrounds', '#the-background-size',\
 'background-size')}}</td>
   <td>{{Spec2('CSS3 Backgrounds')}}</td>
   <td></td>
  </tr>"""

sample_spec_section = """\
<h2 id="Specifications" name="Specifications">Specifications</h2>
<table class="standard-table">
 <thead>
  <tr>
   <th scope="col">Specification</th>
   <th scope="col">Status</th>
   <th scope="col">Comment</th>
  </tr>
 </thead>
 <tbody>
  %s
 </tbody>
</table>
""" % sample_spec_row

sample_compat_section = """\
<h2 id="Browser_compatibility">Browser compatibility</h2>
<div>{{CompatibilityTable}}</div>
<div id="compat-desktop">
 <table class="compat-table">
  <tbody>
   <tr><th>Feature</th><th>Firefox (Gecko)</th></tr>
   <tr><td>Basic support</td><td>{{CompatGeckoDesktop("1")}}</td></tr>
  </tbody>
 </table>
</div>
"""


class TestEndOfLine(TestCase):
    def setUp(self):
        self.text = """\
    This is some sample text.
  Each line is 30 characters,
  when you count the newline:
12345678911234567892123456789"""

    def test_middle_of_text(self):
        end = end_of_line(self.text, 50)
        self.assertEqual(59, end)

    def test_end_of_text(self):
        end = end_of_line(self.text, len(self.text) - 2)
        self.assertEqual(len(self.text), end)


class TestPageVisitor(TestCase):
    def setUp(self):
        feature = self.get_instance(Feature, 'web-css-background-size')
        self.visitor = PageVisitor(feature)

    def test_doc_no_spec(self):
        doc = '<h2 id="Specless">No specs here</h2>'
        parsed = page_grammar['doc'].parse(doc)
        doc_parts = self.visitor.visit(parsed)
        expected = {
            'locale': 'en', 'specs': [], 'issues': [], 'compat': [],
            'footnotes': None}
        self.assertEqual(expected, doc_parts)
        self.assertEqual([], self.visitor.issues)

    def assert_last_section(self, last_section, issues):
        parsed = page_grammar['last_section'].parse(last_section)
        self.visitor.visit(parsed)
        self.assertEqual(issues, self.visitor.issues)

    def test_last_section_ignored(self):
        last_section = (
            "<h2 id=\"summary\">Summary</h2>\n"
            "<p>In summary, this section is ignored.</p>\n")
        self.assert_last_section(last_section, [])

    def test_last_section_invalid(self):
        last_section = (
            "<h2 id=\"specifications\">Specifications</h2>\n"
            "<p><em>TODO:</em> Specs go here</p>")
        issues = [(
            'section_skipped', 47, 79,
            {'title': 'Specifications', 'rule_name': 'whynospec_start',
             'rule': ('whynospec_start = ks_esc_start "WhyNoSpecStart" _'
                      ' ks_esc_end _')})]
        self.assert_last_section(last_section, issues)

    def test_last_section_valid_specifications(self):
        issues = [('section_missed', 0, 65, {'title': 'Specifications'})]
        self.assert_last_section(sample_spec_section, issues)

    def assert_spec_section(self, spec_section, specs):
        parsed = page_grammar['spec_section'].parse(spec_section)
        self.visitor.visit(parsed)
        self.assertEqual(specs, self.visitor.specs)
        self.assertEqual([], self.visitor.issues)

    def test_spec_section_expected(self):
        spec = self.get_instance(Specification, 'css3_backgrounds')
        parsed_specs = [{
            'specification.id': spec.id,
            'specification.mdn_key': 'CSS3 Backgrounds',
            'section.id': None, 'section.name': 'background-size',
            'section.note': '', 'section.subpath': '#the-background-size'}]
        self.assert_spec_section(sample_spec_section, parsed_specs)

    def test_spec_section_why_no_spec(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/AnimationEvent/initAnimationEvent
        spec = """\
<h2 id="Specifications" name="Specifications">Specifications</h2>
<p>
{{WhyNoSpecStart}}
This method is non-standard and not part of any specification, though it was
present in early drafts of {{SpecName("CSS3 Animations")}}.
{{WhyNoSpecEnd}}
</p>"""
        self.assert_spec_section(spec, [])

    def assert_spec_h2(self, spec_h2, expected_issues):
        parsed = page_grammar['spec_h2'].parse(spec_h2)
        self.visitor.visit(parsed)
        self.assertEqual(expected_issues, self.visitor.issues)

    def test_spec_h2_expected(self):
        self.assert_spec_h2(
            '<h2 name="Specifications" id="Specifications">'
            'Specifications</h2>', [])

    def test_spec_h2_discards_extra(self):
        self.assert_spec_h2(
            '<h2 id="Specifications" name="Specifications" extra="crazy">'
            'Specifications</h2>', [])

    def test_spec_h2_browser_compat(self):
        # Common bug from copying from Browser Compatibility section
        self.assert_spec_h2(
            '<h2 id="Browser_compatibility" name="Browser_compatibility">'
            'Specifications</h2>',
            [('spec_h2_id', 4, 31, {'h2_id': 'Browser_compatibility'}),
             ('spec_h2_name', 31, 59, {'h2_name': 'Browser_compatibility'})])

    def assert_spec_row(self, spec_table, expected_specs, issues):
        parsed = page_grammar['spec_row'].parse(spec_table)
        self.visitor.visit(parsed)
        self.assertEqual(expected_specs, self.visitor.specs)
        self.assertEqual(issues, self.visitor.issues)

    def test_spec_row_mismatch(self):
        spec = self.get_instance(Specification, 'css3_ui')
        spec_row = '''\
<tr>
  <td>{{ SpecName('CSS3 UI', '#cursor', 'cursor') }}</td>
  <td>{{ Spec2('CSS3 Basic UI') }}</td>
  <td>Addition of several keywords and the positioning syntax for\
 <code>url()</code>.</td>
</tr>'''
        expected_specs = [{
            'section.note': (
                'Addition of several keywords and the positioning syntax for'
                ' <code>url()</code>.'),
            'section.subpath': '#cursor',
            'section.name': 'cursor',
            'specification.mdn_key': 'CSS3 UI',
            'section.id': None,
            'specification.id': spec.id}]
        issues = [
            ('unknown_spec', 69, 97, {'key': u'CSS3 Basic UI'}),
            ('spec_mismatch', 0, 199,
             {'spec2_key': 'CSS3 Basic UI', 'specname_key': 'CSS3 UI'})]
        self.assert_spec_row(spec_row, expected_specs, issues)

    def test_spec_row_known_spec(self):
        spec = self.get_instance(Specification, 'css3_backgrounds')
        self.create(Section, specification=spec)
        expected_specs = [{
            'section.note': '',
            'section.subpath': '#the-background-size',
            'section.name': 'background-size',
            'specification.mdn_key': 'CSS3 Backgrounds',
            'section.id': None,
            'specification.id': spec.id}]
        self.assert_spec_row(sample_spec_row, expected_specs, [])

    def test_spec_row_known_spec_and_section(self):
        section = self.get_instance(Section, 'background-size')
        spec = section.specification
        expected_specs = [{
            'section.note': '',
            'section.subpath': '#the-background-size',
            'section.name': 'background-size',
            'specification.mdn_key': 'CSS3 Backgrounds',
            'section.id': section.id,
            'specification.id': spec.id}]
        self.assert_spec_row(sample_spec_row, expected_specs, [])

    def test_spec_row_es1(self):
        # en-US/docs/Web/JavaScript/Reference/Operators/this
        es1 = self.get_instance(Specification, 'es1')
        spec_row = """\
<tr>
  <td>ECMAScript 1st Edition.</td>
  <td>Standard</td>
  <td>Initial definition.</td>
</tr>"""
        expected_specs = [{
            'section.note': 'Initial definition.',
            'section.subpath': '',
            'section.name': '',
            'specification.mdn_key': 'ES1',
            'section.id': None,
            'specification.id': es1.id}]
        issues = [
            ('specname_converted', 11, 34,
             {'key': 'ES1', 'original': 'ECMAScript 1st Edition.'}),
            ('spec2_converted', 46, 54,
             {'key': 'ES1', 'original': 'Standard'})]
        self.assert_spec_row(spec_row, expected_specs, issues)

    def test_spec_row_nonstandard(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/Promise (fixed)
        spec_row = """\
<tr>
   <td><a href="https://github.com/domenic/promises-unwrapping">\
domenic/promises-unwrapping</a></td>
   <td>Draft</td>
   <td>Standardization work is taking place here.</td>
</tr>"""
        expected_specs = [{
            'section.note': 'Standardization work is taking place here.',
            'section.subpath': '',
            'section.name': '',
            'specification.mdn_key': '',
            'section.id': None,
            'specification.id': None}]
        issues = [
            ('specname_not_kumascript', 69, 96,
             {'original': 'domenic/promises-unwrapping'}),
            ('spec2_converted', 113, 118,
             {'key': '', 'original': 'Draft'})]
        self.assert_spec_row(spec_row, expected_specs, issues)

    def test_spec2_td_no_spec(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/MIDIInput
        spec2_td = '<td>{{Spec2()}}</td>'
        parsed = page_grammar['spec2_td'].parse(spec2_td)
        spec2 = self.visitor.visit(parsed)
        self.assertEqual('', spec2)
        issues = [(
            'kumascript_wrong_args', 4, 15,
            {'name': 'Spec2', 'args': [], 'scope': 'specification maturity',
             'kumascript': '{{Spec2}}', 'min': 1, 'max': 1, 'count': 0,
             'arg_names': ['SpecKey'], 'arg_count': '0 arguments',
             'arg_spec': 'exactly 1 argument (SpecKey)'})]
        self.assertEqual(self.visitor.issues, issues)

    def test_specdesc_td_with_issue(self):
        # https://developer.mozilla.org/en-US/docs/Web/HTML/Element/data
        specdesc_td = "<td>No change from {{Spec2('HTML5 W3C')}}</td>"
        parsed = page_grammar['specdesc_td'].parse(specdesc_td)
        specdesc = self.visitor.visit(parsed)
        expected = "No change from specification HTML5 W3C"
        self.assertEqual(expected, specdesc)
        issues = [
            ('specdesc_spec2_invalid', 19, 41,
             {'name': 'Spec2', 'args': ['HTML5 W3C'],
              'scope': 'specification description',
              'kumascript': '{{Spec2("HTML5 W3C")}}'})]
        self.assertEqual(self.visitor.issues, issues)

    def assert_compat_section(self, compat_section, compat, footnotes, issues):
        parsed = page_grammar['compat_section'].parse(compat_section)
        self.visitor.visit(parsed)
        self.assertEqual(compat, self.visitor.compat)
        self.assertEqual(footnotes, self.visitor.footnotes)
        self.assertEqual(issues, self.visitor.issues)

    def test_compat_section_minimal(self):
        expected_compat = [{
            'name': u'desktop',
            'browsers': [{
                'id': '_Firefox (Gecko)', 'name': 'Firefox',
                'slug': '_Firefox (Gecko)'}],
            'versions': [{
                'browser': '_Firefox (Gecko)', 'id': '_Firefox-1.0',
                'version': '1.0'}],
            'features': [{
                'id': '_basic support', 'name': 'Basic support',
                'slug': 'web-css-background-size_basic_support'}],
            'supports': [{
                'feature': '_basic support',
                'id': '__basic support-_Firefox-1.0',
                'support': 'yes', 'version': '_Firefox-1.0'}]}]
        issues = [('unknown_browser', 185, 200, {'name': 'Firefox (Gecko)'})]
        self.assert_compat_section(
            sample_compat_section, expected_compat, {}, issues)

    def test_compat_section_footnote(self):
        compat_section = """\
<h2 id="Browser_compatibility">Browser compatibility</h2>
<div>{{CompatibilityTable}}</div>
<div id="compat-desktop">
 <table class="compat-table">
  <tbody>
   <tr><th>Feature</th><th>Chrome</th></tr>
   <tr><td>Basic support</td><td>1.0 [1]</td></tr>
  </tbody>
 </table>
</div>
<p>[1] This is a footnote.</p>
"""
        expected_compat = [{
            'name': u'desktop',
            'browsers': [{
                'id': '_Chrome', 'name': 'Chrome', 'slug': '_Chrome'}],
            'versions': [{
                'browser': '_Chrome', 'id': '_Chrome-1.0', 'version': '1.0'}],
            'features': [{
                'id': '_basic support', 'name': 'Basic support',
                'slug': 'web-css-background-size_basic_support'}],
            'supports': [{
                'feature': '_basic support',
                'id': '__basic support-_Chrome-1.0',
                'support': 'yes', 'version': '_Chrome-1.0',
                'footnote': 'This is a footnote.',
                'footnote_id': ('1', 239, 242)}]}]
        issues = [('unknown_browser', 185, 191, {'name': 'Chrome'})]
        self.assert_compat_section(compat_section, expected_compat, {}, issues)

    def test_compat_section_footnote_mismatch(self):
        compat_section = """\
<h2 id="Browser_compatibility">Browser compatibility</h2>
<div>{{CompatibilityTable}}</div>
<div id="compat-desktop">
 <table class="compat-table">
  <tbody>
   <tr><th>Feature</th><th>Chrome</th></tr>
   <tr><td>Basic support</td><td>3.0 [1]</td></tr>
  </tbody>
 </table>
</div>
<p>[2] Oops, footnote ID is wrong.</p>
"""
        expected_compat = [{
            'name': u'desktop',
            'browsers': [{
                'id': '_Chrome', 'name': 'Chrome', 'slug': '_Chrome'}],
            'versions': [{
                'browser': '_Chrome', 'id': '_Chrome-3.0', 'version': '3.0'}],
            'features': [{
                'id': '_basic support', 'name': 'Basic support',
                'slug': 'web-css-background-size_basic_support'}],
            'supports': [{
                'feature': '_basic support',
                'id': '__basic support-_Chrome-3.0',
                'support': 'yes', 'version': '_Chrome-3.0',
                'footnote_id': ('1', 239, 242)}]}]
        footnotes = {'2': ('Oops, footnote ID is wrong.', 281, 319)}
        issues = [
            ('unknown_browser', 185, 191, {'name': 'Chrome'}),
            ('footnote_missing', 239, 242, {'footnote_id': '1'}),
            ('footnote_unused', 281, 319, {'footnote_id': '2'})]
        self.assert_compat_section(
            compat_section, expected_compat, footnotes, issues)

    def assert_compat_headers(self, compat_headers, expected, issues):
        parsed = page_grammar['compat_headers'].parse(compat_headers)
        headers = self.visitor.visit(parsed)
        self.assertEqual(expected, headers)
        self.assertEqual(issues, self.visitor.issues)

    def test_compat_headers_unknown_browser(self):
        compat_headers = "<tr><th>Feature</th><th>Firefox</th></tr>"
        expected = [{'slug': '_Firefox', 'name': 'Firefox', 'id': "_Firefox"}]
        issues = [('unknown_browser', 24, 31, {'name': 'Firefox'})]
        self.assert_compat_headers(compat_headers, expected, issues)

    def test_compat_headers_known_browser(self):
        firefox = self.get_instance(Browser, 'firefox')
        compat_headers = "<tr><th>Feature</th><th>Firefox</th></tr>"
        expected = [{'slug': 'firefox', 'name': 'Firefox', 'id': firefox.id}]
        self.assert_compat_headers(compat_headers, expected, [])

    def test_compat_headers_strong(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage
        firefox = self.get_instance(Browser, 'firefox')
        compat_headers = (
            "<tr><th><strong>Feature</strong></th>"
            "<th><strong>Firefox</strong></th></tr>")
        expected = [{'slug': 'firefox', 'name': 'Firefox', 'id': firefox.id}]
        self.assert_compat_headers(compat_headers, expected, [])

    def test_compat_headers_wrong_first_column_header(self):
        # All known pages use "Feature" for first column, but be ready
        firefox = self.get_instance(Browser, 'firefox')
        compat_headers = (
            "<tr><th><strong>Features</strong></th>"
            "<th><strong>Firefox</strong></th></tr>")
        expected = [{'slug': 'firefox', 'name': 'Firefox', 'id': firefox.id}]
        issues = [(
            'feature_header', 16, 24, {'header': 'Features'})]
        self.assert_compat_headers(compat_headers, expected, issues)

    def test_compat_headers_with_colspan(self):
        # https://developer.mozilla.org/en-US/Web/CSS/background-size
        compat_headers = (
            "<tr><th>Feature</th>"
            "<th colspan=\"3\">Safari (WebKit)</th></tr>")
        expected = [{
            'slug': '_Safari (WebKit)',
            'name': 'Safari',
            'id': '_Safari (WebKit)',
            'colspan': '3'
        }]
        issues = [('unknown_browser', 36, 51, {'name': 'Safari (WebKit)'})]
        self.assert_compat_headers(compat_headers, expected, issues)

    def test_compat_headers_with_line_height(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/Navigator/serviceWorker
        chrome = self.get_instance(Browser, 'chrome')
        compat_headers = (
            '<tr><th style="line-height: 16px;">Feature</th>'
            '<th style="line-height: 16px;">Chrome</th></tr>')
        expected = [{'slug': 'chrome', 'name': 'Chrome', 'id': chrome.id}]
        issues = [
            ('unexpected_attribute', 51, 77,
             {'node_type': 'th', 'ident': 'style',
              'value': 'line-height: 16px;',
              'expected': 'the attribute colspan'})]
        self.assert_compat_headers(compat_headers, expected, issues)

    def assert_compat_row_cell(self, row_cell, expected_cell, issues):
        parsed = page_grammar['compat_row_cell'].parse(row_cell)
        cell = self.visitor.visit(parsed)
        self.assertEqual(expected_cell, cell)
        self.assertEqual(issues, self.visitor.issues)

    def test_compat_row_cell_feature_with_rowspan(self):
        row_cell = '<td rowspan="2">Some Feature</td>'
        expected_cell = {
            'type': 'td', 'start': 0, 'end': 33, 'rowspan': '2', 'content': {
                'type': 'text', 'start': 16, 'end': 28,
                'content': 'Some Feature'}}
        self.assert_compat_row_cell(row_cell, expected_cell, [])

    def test_compat_row_cell_feature_with_unknown_attr(self):
        row_cell = '<td class="freaky">Freaky Feature</td>'
        expected_cell = {
            'type': 'td', 'start': 0, 'end': 38, 'content': {
                'type': 'text', 'start': 19, 'end': 33,
                'content': 'Freaky Feature'}}
        issues = [(
            'unexpected_attribute', 4, 18,
            {'node_type': 'td', 'ident': 'class', 'value': 'freaky',
             'expected': 'the attributes rowspan or colspan'})]
        self.assert_compat_row_cell(row_cell, expected_cell, issues)

    def test_compat_row_break(self):
        row_cell = '<td>Multi-line<br/>feature</td>'
        expected_cell = {
            'type': 'td', 'start': 0, 'end': 31, 'content': {
                'type': 'html_block', 'start': 4, 'end': 26, 'content': [
                    {'type': 'text', 'start': 4, 'end': 14,
                     'content': 'Multi-line'},
                    {'type': 'break', 'start': 14, 'end': 19},
                    {'type': 'text', 'start': 19, 'end': 26,
                     'content': 'feature'},
                ]}}
        self.assert_compat_row_cell(row_cell, expected_cell, [])

    def test_compat_row_cell_kumascript(self):
        row_cell = '<td>EXP {{experimental_inline}} FEATURE</td>'
        expected_cell = {
            'type': 'td', 'start': 0, 'end': 44, 'content': {
                'type': 'text_block', 'start': 4, 'end': 39, 'content': [
                    {'type': 'text', 'start': 4, 'end': 8, 'content': 'EXP '},
                    {'type': 'kumascript', 'start': 8, 'end': 32,
                     'name': 'experimental_inline', 'args': []},
                    {'type': 'text', 'start': 32, 'end': 39,
                     'content': 'FEATURE'}]}}
        self.assert_compat_row_cell(row_cell, expected_cell, [])

    def test_compat_row_code_block(self):
        row_cell = '<td><code>canonical</code></td>'
        expected_cell = {
            'type': 'td', 'start': 0, 'end': 31, 'content': {
                'type': 'code', 'start': 4, 'end': 26, 'attributes': {},
                'content': {
                    'type': 'text', 'start': 10, 'end': 19,
                    'content': 'canonical'}}}
        self.assert_compat_row_cell(row_cell, expected_cell, [])

    def assert_cell_to_feature(
            self, contents, expected_feature, issues):
        row_cell = "<td>%s</td>" % contents
        parsed = page_grammar['compat_row_cell'].parse(row_cell)
        cell = self.visitor.visit(parsed)
        feature = self.visitor.cell_to_feature(cell)
        self.assertEqual(expected_feature, feature)
        self.assertEqual(issues, self.visitor.issues)

    def test_cell_to_feature_remove_whitespace(self):
        cell = (
            ' Support for<br>\n     <code>contain</code> and'
            ' <code>cover</code> ')
        expected_feature = {
            'id': '_support for contain and cover',
            'name': 'Support for <code>contain</code> and <code>cover</code>',
            'slug': 'web-css-background-size_support_for_contain_and_co',
        }
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_code_sequence(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/display
        cell = (
            '<code>none</code>, <code>inline</code> and'
            ' <code>block</code>')
        expected_feature = {
            'id': '_none, inline and block',
            'name': (
                '<code>none</code>, <code>inline</code> and'
                ' <code>block</code>'),
            'slug': 'web-css-background-size_none_inline_and_block'}
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_canonical(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/display
        cell = '<code>list-item</code>'
        expected_feature = {
            'id': '_list-item', 'name': 'list-item', 'canonical': True,
            'slug': 'web-css-background-size_list-item'}
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_canonical_match(self):
        feature = self.create(
            Feature, parent=self.visitor.feature,
            name={'zxx': 'list-item'}, slug='slug-list-item')
        cell = '<code>list-item</code>'
        expected_feature = {
            'id': feature.id, 'name': 'list-item', 'slug': 'slug-list-item',
            'canonical': True,
        }
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_ks_experimental(self):
        cell = '<code>grid</code> {{experimental_inline}}'
        expected_feature = {
            'id': '_grid', 'name': 'grid', 'canonical': True,
            'experimental': True, 'slug': 'web-css-background-size_grid'}
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_ks_non_standard_inline(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/AnimationEvent
        cell = '<code>initAnimationEvent()</code> {{non-standard_inline}}'
        expected_feature = {
            'id': '_initanimationevent()', 'name': 'initAnimationEvent()',
            'canonical': True, 'standardized': False,
            'slug': 'web-css-background-size_initanimationevent_'}
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_ks_deprecated_inline(self):
        cell = '<code>initAnimationEvent()</code> {{deprecated_inline}}'
        expected_feature = {
            'id': '_initanimationevent()', 'name': 'initAnimationEvent()',
            'canonical': True, 'obsolete': True,
            'slug': 'web-css-background-size_initanimationevent_'}
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_ks_htmlelement(self):
        cell = '{{ HTMLElement("progress") }}'
        expected_feature = {
            'id': '_progress', 'name': '&lt;progress&gt;',
            'canonical': True,
            'slug': 'web-css-background-size_progress',
        }
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_ks_domxref(self):
        cell = '{{domxref("DeviceProximityEvent")}}'
        expected_feature = {
            'id': '_deviceproximityevent', 'name': 'DeviceProximityEvent',
            'slug': 'web-css-background-size_deviceproximityevent',
            'canonical': True
        }
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_unknown_kumascript(self):
        cell = 'feature foo {{bar}}'
        expected_feature = {
            'id': '_feature foo', 'name': 'feature foo',
            'slug': 'web-css-background-size_feature_foo'}
        issues = [
            ('unknown_kumascript', 16, 23,
             {'name': 'bar', 'args': [], 'kumascript': '{{bar}}',
              'scope': 'feature'})]
        self.assert_cell_to_feature(cell, expected_feature, issues)

    def test_cell_to_feature_unknown_kumascript_with_args(self):
        cell = 'foo {{bar("baz")}}'
        expected_feature = {
            'id': '_foo', 'name': 'foo', 'slug': 'web-css-background-size_foo'}
        issues = [
            ('unknown_kumascript', 8, 22,
             {'name': 'bar', 'args': ['baz'], 'kumascript': '{{bar(baz)}}',
              'scope': 'feature'})]
        self.assert_cell_to_feature(cell, expected_feature, issues)

    def test_cell_to_feature_nonascii_name(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/font-variant
        cell = '<code>ß</code> → <code>SS</code>'
        expected_feature = {
            'id': '_\xdf \u2192 ss',
            'name': '<code>\xdf</code> \u2192 <code>SS</code>',
            'slug': 'web-css-background-size_ss'}
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_footnote(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/text-align
        cell = 'Block alignment values [1] {{not_standard_inline}}'
        expected_feature = {
            'id': '_block alignment values', 'name': 'Block alignment values',
            'standardized': False,
            'slug': 'web-css-background-size_block_alignment_values'}
        issues = [('footnote_feature', 27, 30, {})]
        self.assert_cell_to_feature(cell, expected_feature, issues)

    def test_cell_to_feature_digit(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/transform
        cell = '3D Support'
        expected_feature = {
            'id': '_3d support', 'name': '3D Support',
            'slug': 'web-css-background-size_3d_support'
        }
        self.assert_cell_to_feature(cell, expected_feature, [])

    def test_cell_to_feature_link(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/EventSource
        cell = ('<a href="/En/HTTP_access_control">'
                'Cross-Origin Resource Sharing</a><br>')
        expected_feature = {
            'id': '_cross-origin resource sharing',
            'name': 'Cross-Origin Resource Sharing',
            'slug': 'web-css-background-size_cross-origin_resource_shar'
        }
        issues = [('tag_dropped', 4, 71, {'tag': 'a', 'scope': 'feature'})]
        self.assert_cell_to_feature(cell, expected_feature, issues)

    def test_cell_to_feature_p(self):
        # https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/const
        cell = ('<p>Reassignment fails</p>')
        expected_feature = {
            'id': '_reassignment fails',
            'name': 'Reassignment fails',
            'slug': 'web-css-background-size_reassignment_fails'
        }
        issues = [('tag_dropped', 4, 29, {'tag': 'p', 'scope': 'feature'})]
        self.assert_cell_to_feature(cell, expected_feature, issues)

    def test_cell_to_feature_unknown_item(self):
        bad_cell = {'type': 'td', 'content': {'type': 'other'}}
        self.assertRaises(ValueError, self.visitor.cell_to_feature, bad_cell)

    def assert_cell_to_support_full(
            self, row_cell, feature_rep, browser_rep, expected_versions,
            expected_supports, issues):
        """Complete test of cell_to_support."""
        parsed = page_grammar['compat_row_cell'].parse(row_cell)
        cell = self.visitor.visit(parsed)
        versions, supports = self.visitor.cell_to_support(
            cell, feature_rep, browser_rep)
        self.assertEqual(expected_versions, versions)
        self.assertEqual(expected_supports, supports)
        self.assertEqual(issues, self.visitor.issues)

    def get_feature_rep(self, feature):
        """Create the visitor representation of a feature"""
        return {
            'id': feature.id, 'name': feature.name['en'], 'slug': feature.slug}

    def get_browser_rep(self, browser):
        """Create the visitor representation of a browser"""
        return {
            'id': browser.id, 'name': browser.name['en'], 'slug': browser.slug}

    def test_cell_to_support_matched_version(self):
        version = self.get_instance(Version, ('firefox', '1.0'))
        browser = version.browser
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')

        row_cell = "<td>1.0</td>"
        feature_rep = self.get_feature_rep(feature)
        browser_rep = self.get_browser_rep(browser)
        expected_versions = [{
            'id': version.id, 'version': version.version,
            'browser': browser.id}]
        expected_supports = [{
            'id': '_%s-%s' % (feature.id, version.id),
            'support': "yes", 'version': version.id, 'feature': feature.id}]
        self.assert_cell_to_support_full(
            row_cell, feature_rep, browser_rep, expected_versions,
            expected_supports, [])

    def test_cell_to_support_unknown_version(self):
        browser = self.get_instance(Browser, 'firefox')

        row_cell = "<td>1.0</td>"
        feature_rep = {'id': '_feature', 'name': 'feature', 'slug': 'fslug'}
        browser_rep = self.get_browser_rep(browser)
        expected_versions = [{
            'id': '_Firefox-1.0', 'version': '1.0', 'browser': browser.id}]
        expected_supports = [{
            'id': '__feature-_Firefox-1.0', 'support': "yes",
            'version': '_Firefox-1.0', 'feature': '_feature'}]
        issues = [
            ('unknown_version', 4, 7,
             {'version': '1.0', 'browser_id': browser.id,
              'browser_name': 'Firefox', 'browser_slug': 'firefox'})]
        self.assert_cell_to_support_full(
            row_cell, feature_rep, browser_rep, expected_versions,
            expected_supports, issues)

    def test_cell_to_support_matched_support(self):
        version = self.get_instance(Version, ('firefox', '1.0'))
        browser = version.browser
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')
        support = self.create(Support, version=version, feature=feature)

        row_cell = "<td>1.0</td>"
        feature_rep = self.get_feature_rep(feature)
        browser_rep = self.get_browser_rep(browser)
        expected_versions = [{
            'id': version.id, 'version': version.version,
            'browser': browser.id}]
        expected_supports = [{
            'id': support.id, 'support': "yes", 'version': version.id,
            'feature': feature.id}]
        self.assert_cell_to_support_full(
            row_cell, feature_rep, browser_rep, expected_versions,
            expected_supports, [])

    def test_compat_row_cell_support_compatversionunknown_vmatch(self):
        version = self.get_instance(Version, ('firefox', 'current'))
        browser = version.browser
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')

        row_cell = "<td>{{CompatVersionUnknown}}</td>"
        feature_rep = self.get_feature_rep(feature)
        browser_rep = self.get_browser_rep(browser)
        expected_versions = [{
            'id': version.id, 'browser': browser.id, 'version': 'current'}]
        expected_supports = [{
            'id': '_%s-%s' % (feature.id, version.id),
            'version': version.id, 'feature': feature.id, 'support': "yes"}]
        self.assert_cell_to_support_full(
            row_cell, feature_rep, browser_rep, expected_versions,
            expected_supports, [])

    def assert_cell_to_support(
            self, contents, expected_versions=[], expected_supports=[],
            issues=[]):
        """Test cell_to_support with helpful defaults."""
        row_cell = "<td>%s</td>" % contents
        feature_rep = {'id': '_feature', 'name': 'feature', 'slug': 'fslug'}
        browser_rep = {'id': '_browser', 'name': 'Browser', 'slug': 'browser'}
        for ev in expected_versions:
            assert 'id' not in ev
            assert 'browser' not in ev
            ev['id'] = '_%s-%s' % (browser_rep['name'], ev['version'])
            ev['browser'] = browser_rep['id']
        for i, es in enumerate(expected_supports):
            version = expected_versions[i]
            assert 'id' not in es
            assert 'version' not in es
            assert 'feature' not in es
            es['id'] = '_%s-%s' % (feature_rep['id'], version['id'])
            es['version'] = version['id']
            es['feature'] = feature_rep['id']
        self.assert_cell_to_support_full(
            row_cell, feature_rep, browser_rep,
            expected_versions, expected_supports, issues)

    def test_cell_to_support_version(self):
        self.assert_cell_to_support(
            '1.0',
            [{'version': '1.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatno(self):
        self.assert_cell_to_support(
            '{{CompatNo}}',
            [{'version': 'current'}], [{'support': 'no'}])

    def test_cell_to_support_compatversionunknown(self):
        self.assert_cell_to_support(
            '{{CompatVersionUnknown}}',
            [{'version': 'current'}], [{'support': 'yes'}])

    def test_cell_to_support_compatunknown(self):
        self.assert_cell_to_support('{{CompatUnknown}}', [], [])

    def test_cell_to_support_compatgeckodesktop_10(self):
        self.assert_cell_to_support(
            '{{CompatGeckoDesktop("1")}}',
            [{'version': '1.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckodesktop_8(self):
        self.assert_cell_to_support(
            '{{CompatGeckoDesktop("8.0")}}',
            [{'version': '8.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckodesktop_bad_text(self):
        self.assert_cell_to_support(
            '{{CompatGeckoDesktop("Yep")}}',
            issues=[('compatgeckodesktop_unknown', 4, 33, {'version': 'Yep'})])

    def test_cell_to_support_compatgeckodesktop_bad_num(self):
        self.assert_cell_to_support(
            '{{CompatGeckoDesktop("1.1")}}',
            issues=[('compatgeckodesktop_unknown', 4, 33, {'version': '1.1'})])

    def test_cell_to_support_compatgeckofxos_7(self):
        self.assert_cell_to_support(
            '{{CompatGeckoFxOS("7")}}',
            [{'version': '1.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckofxos_7_version_1_0_1(self):
        self.assert_cell_to_support(
            '{{CompatGeckoFxOS("7","1.0.1")}}',
            [{'version': '1.0.1'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckofxos_7_version_1_1(self):
        self.assert_cell_to_support(
            '{{CompatGeckoFxOS("7","1.1")}}',
            [{'version': '1.1'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckofxos_range(self):
        versions = {'10': '1.0',
                    '24': '1.2',
                    '28': '1.3',
                    '29': '1.4',
                    '32': '2.0',
                    '34': '2.1',
                    '35': '2.2'
                    }
        for gversion, oversion in versions.items():
            self.assert_cell_to_support(
                '{{CompatGeckoFxOS("%s")}}' % gversion,
                [{'version': oversion}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckofxos_bad_gecko(self):
        self.assert_cell_to_support(
            '{{CompatGeckoFxOS("999999")}}',
            issues=[('compatgeckofxos_unknown', 4, 33, {'version': '999999'})])

    def test_cell_to_support_compatgeckofxos_bad_text(self):
        self.assert_cell_to_support(
            '{{CompatGeckoFxOS("Yep")}}',
            issues=[('compatgeckofxos_unknown', 4, 30, {'version': 'Yep'})])

    def test_cell_to_support_compatgeckofxos_bad_version(self):
        self.assert_cell_to_support(
            '{{CompatGeckoFxOS("18","5.0")}}',
            issues=[('compatgeckofxos_override', 4, 35,
                     {'override': '5.0', 'version': '18'})])

    def test_cell_to_support_compatgeckomobile_1(self):
        self.assert_cell_to_support(
            '{{CompatGeckoMobile("1")}}',
            [{'version': '1.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckomobile_1_11(self):
        self.assert_cell_to_support(
            '{{CompatGeckoMobile("1.11")}}',
            [{'version': '1.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatgeckomobile_2(self):
        self.assert_cell_to_support(
            '{{CompatGeckoMobile("2")}}',
            [{'version': '4.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatandroid_3(self):
        self.assert_cell_to_support(
            '{{CompatAndroid("3.0")}}',
            [{'version': '3.0'}], [{'support': 'yes'}])

    def test_cell_to_support_compatnightly(self):
        self.assert_cell_to_support(
            '{{CompatNightly}}',
            [{'version': 'nightly'}], [{'support': 'yes'}])

    def test_cell_to_support_unknown_kumascript(self):
        issues = [(
            'unknown_kumascript', 4, 19,
            {'name': 'UnknownKuma', 'args': [], 'scope': 'compatibility cell',
             'kumascript': "{{UnknownKuma}}"})]
        self.assert_cell_to_support('{{UnknownKuma}}', issues=issues)

    def test_cell_to_support_unknown_kumascript_args(self):
        issues = [(
            'unknown_kumascript', 4, 26,
            {'name': 'UnknownKuma', 'args': ['foo'],
             'scope': 'compatibility cell',
             'kumascript': "{{UnknownKuma(foo)}}"})]
        self.assert_cell_to_support('{{UnknownKuma("foo")}}', issues=issues)

    def test_cell_to_support_nested_p(self):
        self.assert_cell_to_support(
            '<p><p>4.0</p></p>',
            issues=[('nested_p', 7, 17, {})])

    def test_cell_to_support_with_prefix_and_break(self):
        self.assert_cell_to_support(
            ('{{CompatVersionUnknown}}{{property_prefix("-webkit")}}<br>\n'
             '   2.3'),
            [{'version': 'current'}, {'version': '2.3'}],
            [{'support': 'yes', 'prefix': '-webkit'}, {'support': 'yes'}])

    def test_cell_to_support_p_tags(self):
        self.assert_cell_to_support(
            '<p>4.0</p><p>32</p>',
            [{'version': '4.0'}, {'version': '32.0'}],
            [{'support': 'yes'}, {'support': 'yes'}])

    def test_cell_to_support_two_line_note(self):
        self.assert_cell_to_support(
            '18<br>\n(behind a pref) [1]',
            [{'version': '18.0'}],
            [{'support': 'yes', 'footnote_id': ('1', 27, 30)}],
            issues=[('inline_text', 11, 27, {'text': '(behind a pref)'})])

    def test_cell_to_support_removed_in_gecko(self):
        self.assert_cell_to_support(
            ('{{ CompatGeckoMobile("6.0") }}<br>'
             'Removed in {{ CompatGeckoMobile("23.0") }}'),
            [{'version': '6.0'}, {'version': '23.0'}],
            [{'support': 'yes'}, {'support': 'no'}])

    def test_cell_to_support_removed_in_version(self):
        self.assert_cell_to_support(
            'Removed in 32',
            [{'version': '32.0'}], [{'support': 'no'}])

    def test_cell_to_support_unprefixed(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/AudioContext.createBufferSource
        self.assert_cell_to_support(
            '32 (unprefixed)',
            [{'version': '32.0'}], [{'support': 'yes'}])

    def test_cell_to_support_partial(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/IDBCursor
        self.assert_cell_to_support(
            '10, partial',
            [{'version': '10.0'}], [{'support': 'partial'}])

    def test_cell_to_support_unmatched_free_text(self):
        self.assert_cell_to_support(
            '32 (or earlier)',
            [{'version': '32.0'}], [{'support': 'yes'}],
            issues=[('inline_text', 7, 19, {'text': '(or earlier)'})])

    def test_cell_to_support_code_block(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/order
        self.assert_cell_to_support(
            '32 with alt name <code>foobar</code>',
            [{'version': '32.0'}], [{'support': 'yes'}],
            issues=[
                ('inline_text', 7, 21, {'text': 'with alt name'}),
                ('inline_text', 21, 40, {'text': '<code>foobar</code>'})])

    def test_cell_to_support_spaces(self):
        self.assert_cell_to_support('  ')

    def test_cell_to_support_prefix_plus_footnote(self):
        self.assert_cell_to_support(
            '18{{property_prefix("-webkit")}} [1]',
            [{'version': '18.0'}],
            [{'support': 'partial', 'prefix': '-webkit',
              'footnote_id': ('1', 37, 40)}])

    def test_cell_to_support_prefix_double_footnote(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/CSSSupportsRule
        self.assert_cell_to_support(
            '{{ CompatGeckoDesktop("17") }} [1][2]',
            [{'version': '17.0'}],
            [{'support': 'yes', 'footnote_id': ('1', 35, 38)}],
            issues=[('footnote_multiple', 38, 41,
                     {'prev_footnote_id': '1', 'footnote_id': '2'})])

    def test_cell_to_support_double_footnote_link_sup(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/flex
        self.assert_cell_to_support(
            '{{CompatGeckoDesktop("20.0")}} '
            '<sup><a href="#bc2">[2]</a><a href="#bc3">[3]</a></sup>',
            [{'version': '20.0'}],
            [{'support': 'yes', 'footnote_id': ('2', 55, 58)}],
            issues=[('footnote_multiple', 77, 80,
                    {'prev_footnote_id': '2', 'footnote_id': '3'})])

    def test_cell_to_support_star_footnote(self):
        self.assert_cell_to_support(
            '{{CompatGeckoDesktop("20.0")}} [***]',
            [{'version': '20.0'}],
            [{'support': 'yes', 'footnote_id': ('3', 35, 40)}])

    def test_cell_to_support_nbsp(self):
        self.assert_cell_to_support(
            '15&nbsp;{{property_prefix("webkit")}}',
            [{'version': '15.0'}], [{'support': 'yes', 'prefix': 'webkit'}])

    def test_cell_to_support_unknown_item(self):
        feature = {'id': '_feature', 'name': 'feature', 'slug': 'feature_slug'}
        browser = {'id': '_browser', 'name': 'Browser', 'slug': 'browser'}
        bad_cell = {'type': 'td', 'content': {'type': 'other'}}
        self.assertRaises(
            ValueError, self.visitor.cell_to_support, bad_cell, feature,
            browser)

    def assert_compat_body(self, compat_body, expected, issues):
        parsed = page_grammar['compat_body'].parse(compat_body)
        body = self.visitor.visit(parsed)
        self.assertEqual(expected, body)
        self.assertEqual(issues, self.visitor.issues)

    def test_compat_body_success(self):
        chrome_10 = self.get_instance(Version, ('chrome', '1.0'))
        chrome = chrome_10.browser
        compat_body = """<tbody>
            <tr><th>Feature</th><th>Chrome</th></tr>
            <tr><td>Basic support</td><td>1.0</td></tr>
        </tbody>"""
        expected = {
            'browsers': [
                {'id': chrome.id, 'name': 'Chrome', 'slug': 'chrome'}],
            'features': [{
                'id': '_basic support', 'name': 'Basic support',
                'slug': 'web-css-background-size_basic_support'}],
            'supports': [{
                'feature': '_basic support',
                'id': '__basic support-%s' % chrome_10.id,
                'support': 'yes', 'version': chrome_10.id}],
            'versions': [{
                'browser': chrome.id, 'id': chrome_10.id, 'version': '1.0'}]}
        self.assert_compat_body(compat_body, expected, [])

    def test_compat_body_extra_feature_column(self):
        # https://developer.mozilla.org/en-US/docs/Web/JavaScript/
        # Reference/Global_Objects/WeakSet, March 2015
        chrome_10 = self.get_instance(Version, ('chrome', '1.0'))
        chrome = chrome_10.browser
        compat_body = """<tbody>
            <tr>
                <th>Feature</th><th>Chrome</th>
            </tr>
            <tr>
                <td>Basic support</td><td>1.0</td><td>{{CompatUnknown()}}</td>
            </tr>
            </tbody>"""
        expected = {
            'browsers': [{
                'id': chrome.id, 'name': 'Chrome', 'slug': 'chrome'}],
            'features': [{
                'id': '_basic support', 'name': 'Basic support',
                'slug': 'web-css-background-size_basic_support'}],
            'supports': [{
                'feature': '_basic support',
                'id': '__basic support-%s' % chrome_10.id,
                'support': 'yes', 'version': chrome_10.id}],
            'versions': [{
                'browser': chrome.id, 'id': chrome_10.id, 'version': '1.0'}]}
        issues = [('extra_cell', 158, 186, {})]
        self.assert_compat_body(compat_body, expected, issues)

    def assert_compat_footnotes(self, compat_footnotes, expected, issues):
        parsed = page_grammar['compat_footnotes'].parse(compat_footnotes)
        footnotes = self.visitor.visit(parsed)
        self.assertEqual(expected, footnotes)
        self.assertEqual(issues, self.visitor.issues)

    def test_compat_footnotes_empty(self):
        footnotes = '\n'
        expected = {}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_simple(self):
        footnotes = "<p>[1] A footnote.</p>"
        expected = {'1': ('A footnote.', 0, 22)}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_multi_paragraph(self):
        footnotes = "<p>[1] Footnote line 1.</p><p>Footnote line 2.</p>"
        expected = {
            '1': ("<p>Footnote line 1.</p>\n<p>Footnote line 2.</p>", 0, 50)}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_multiple_footnotes(self):
        footnotes = "<p>[1] Footnote 1.</p><p>[2] Footnote 2.</p>"
        expected = {'1': ('Footnote 1.', 0, 22), '2': ('Footnote 2.', 22, 44)}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_kumascript_cssxref(self):
        footnotes = '<p>[1] Use {{cssxref("-moz-border-image")}}</p>'
        expected = {'1': ('Use <code>-moz-border-image</code>', 0, 47)}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_unknown_kumascriptscript(self):
        footnotes = (
            "<p>[1] Footnote {{UnknownKuma}} but the beat continues.</p>")
        expected = {'1': ('Footnote but the beat continues.', 0, 59)}
        issues = [(
            'unknown_kumascript', 16, 32,
            {'name': 'UnknownKuma', 'args': [], 'scope': 'footnote',
             'kumascript': '{{UnknownKuma}}'})]
        self.assert_compat_footnotes(footnotes, expected, issues)

    def test_compat_footnotes_unknown_kumascriptscript_with_args(self):
        footnotes = '<p>[1] Footnote {{UnknownKuma("arg")}}</p>'
        expected = {'1': ('Footnote', 0, 42)}
        issues = [(
            'unknown_kumascript', 16, 38,
            {'name': 'UnknownKuma', 'args': ['arg'], 'scope': 'footnote',
             'kumascript': '{{UnknownKuma(arg)}}'})]
        self.assert_compat_footnotes(footnotes, expected, issues)

    def test_compat_footnotes_pre_section(self):
        footnotes = '<p>[1] Here\'s some code:</p><pre>foo = bar</pre>'
        expected = {
            '1': ("<p>Here's some code:</p>\n<pre>foo = bar</pre>", 0, 48)}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_pre_with_attrs_section(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/white-space
        footnotes = (
            '<p>[1] Here\'s some code:</p>\n'
            '<pre class="brush:css">\n'
            '.foo {background-image: url(bg-image.png);}\n'
            '</pre>')
        expected = {
            '1': (
                "<p>Here's some code:</p>\n<pre>\n"
                ".foo {background-image: url(bg-image.png);}\n</pre>",
                0, 103)}
        issues = [
            ('unexpected_attribute', 34, 51,
             {'ident': 'class', 'node_type': 'pre', 'value': 'brush:css',
              'expected': 'no attributes'})]
        self.assert_compat_footnotes(footnotes, expected, issues)

    def test_compat_footnotes_asterisk(self):
        footnotes = "<p>[*] A footnote</p>"
        expected = {'1': ('A footnote', 0, 21)}
        self.assert_compat_footnotes(footnotes, expected, [])

    def test_compat_footnotes_bad_footnote(self):
        footnotes = "<p>A footnote.</p>"
        issues = [('footnote_no_id', 0, 18, {})]
        self.assert_compat_footnotes(footnotes, {}, issues)

    def test_compat_footnotes_bad_footnote_unknown_kumascript(self):
        # https://developer.mozilla.org/en-US/docs/Web/SVG/Element/color-profile
        footnotes = '<p>{{SVGRef}}</p>'
        issues = [
            ('unknown_kumascript', 3, 13,
             {'name': 'SVGRef', 'args': [], 'kumascript': '{{SVGRef}}',
              'scope': u'footnote'})]
        self.assert_compat_footnotes(footnotes, {}, issues)

    def test_compat_footnotes_empty_paragraph_no_footnotes(self):
        footnotes = ('<p>  </p>\n')
        self.assert_compat_footnotes(footnotes, {}, [])

    def test_compat_footnotes_empty_paragraph_invalid_footnote(self):
        footnotes = (
            '<p> </p>\n'
            '<p>Invalid footnote.</p>\n'
            '<p>  </p>')
        issues = [('footnote_no_id', 9, 33, {})]
        self.assert_compat_footnotes(footnotes, {}, issues)
        self.assertEqual(footnotes[9:33], '<p>Invalid footnote.</p>')

    def test_compat_footnotes_empty_paragraphs_trimmed(self):
        footnote = (
            '<p> </p>\n'
            '<p>[1] Valid footnote.</p>'
            '<p>   </p>'
            '<p>Continues footnote 1.</p>')
        expected = {
            '1': (
                '<p>Valid footnote.</p>\n<p>Continues footnote 1.</p>',
                9, 73)}
        self.assert_compat_footnotes(footnote, expected, [])

    def test_compat_footnotes_code(self):
        footnote = (
            '<p>[1] From Firefox 31 to 35, <code>will-change</code>'
            ' was available...</p>')
        expected = {
            '1': (
                'From Firefox 31 to 35, <code>will-change</code>'
                ' was available...', 0, 75)}
        self.assert_compat_footnotes(footnote, expected, [])

    def test_compat_footnotes_span(self):
        # https://developer.mozilla.org/en-US/docs/Web/Events/DOMContentLoaded
        footnote = (
            '<p>[1]<span style="font-size: 14px; line-height: 18px;">'
            'Bubbling for this event is supported by at least Gecko 1.9.2,'
            ' Chrome 6, and Safari 4.</span></p>')
        expected = {
            '1': ('Bubbling for this event is supported by at least Gecko'
                  ' 1.9.2, Chrome 6, and Safari 4.', 0, 152)}
        issues = [
            ('span_dropped', 6, 148, {})]
        self.assert_compat_footnotes(footnote, expected, issues)

    def test_compat_footnotes_a(self):
        # https://developer.mozilla.org/en-US/docs/Web/SVG/SVG_as_an_Image
        footnote = (
            '<p>[1] Compatibility data from'
            '<a href="http://caniuse.com" title="http://caniuse.com">'
            'caniuse.com</a>.</p>')
        expected = {
            '1': ('Compatibility data from <a href="http://caniuse.com">'
                  'caniuse.com</a>.', 0, 106)}
        issues = [
            ('unexpected_attribute', 59, 85,
             {'node_type': 'a', 'ident': 'title',
              'value': 'http://caniuse.com',
              'expected': u'the attribute href'})]
        self.assert_compat_footnotes(footnote, expected, issues)

    def test_compat_footnotes_a_without_href(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/VRFieldOfViewReadOnly/downDegrees
        footnote = '<p>[1] Use <a>about:config</a></p>'
        expected = {'1': ('Use <a>about:config</a>', 0, 34)}
        issues = [
            ('missing_attribute', 11, 30, {'node_type': 'a', 'ident': 'href'})]
        self.assert_compat_footnotes(footnote, expected, issues)

    def test_compat_footnotes_br_start(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/VRFieldOfViewReadOnly/downDegrees
        footnote = "<p><br>\n[1] To find information on Chrome's WebVR...</p>"
        expected = {'1': ("To find information on Chrome's WebVR...", 0, 56)}
        self.assert_compat_footnotes(footnote, expected, [])

    def test_compat_footnotes_br_end(self):
        # https://developer.mozilla.org/en-US/docs/Web/Events/wheel
        footnote = "<p>[1] Here's a footnote. <br></p>"
        expected = {'1': ("Here's a footnote.", 0, 34)}
        self.assert_compat_footnotes(footnote, expected, [])

    def test_compat_footnotes_br_footnotes(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/URLUtils/hash
        footnote = "<p>[1] Footnote 1.<br>[2] Footnote 2.</p>"
        expected = {'1': ("Footnote 1. <br/> Footnote 2.", 0, 41)}
        issues = [('second_footnote', 22, 25, {'original': '1', 'new': '2'})]
        self.assert_compat_footnotes(footnote, expected, issues)

    def test_compat_footnotes_version(self):
        # https://developer.mozilla.org/en-US/docs/Web/Events/focusin
        link = (
            '<a href="https://bugzilla.mozilla.org/show_bug.cgi?id=687787">'
            '687787</a>')  # 687787 triggers the compat cell version pattern
        footnote = '<p>[1] See bug {}.</p>'.format(link)
        expected = {'1': ('See bug {}.'.format(link), 0, 92)}
        self.assert_compat_footnotes(footnote, expected, [])

    def test_compat_footnotes_removed(self):
        # https://developer.mozilla.org/en-US/docs/Web/HTML/Element/style
        footnote = "<p>[1] Removed in Chrome 35+</p>"
        expected = {'1': ('Removed in Chrome 35+', 0, 32)}
        self.assert_compat_footnotes(footnote, expected, [])

    def test_compat_h3(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/MozContact/key
        h3 = '<h3 id="Gecko Gecko">Gecko Note</h3>\n<p>A note</p>'
        parsed = page_grammar['compat_h3'].parse(h3)
        self.visitor.visit(parsed)
        expected = [('skipped_h3', 0, 36, {'h3': 'Gecko Note'})]
        self.assertEqual(expected, self.visitor.issues)

    def assert_kumascript(self, text, name, args, issues=None):
        parsed = page_grammar['kumascript'].parse(text)
        expected = {
            'type': 'kumascript', 'name': name, 'args': args,
            'start': 0, 'end': len(text)}
        self.assertEqual(expected, self.visitor.visit(parsed))
        self.assertEqual(issues or [], self.visitor.issues)

    def test_kumascript_no_parens(self):
        self.assert_kumascript('{{CompatNo}}', 'CompatNo', [])

    def test_kumascript_no_parens_and_spaces(self):
        self.assert_kumascript('{{ CompatNo }}', 'CompatNo', [])

    def test_kumascript_empty_parens(self):
        self.assert_kumascript('{{CompatNo()}}', 'CompatNo', [])

    def test_kumascript_one_arg(self):
        self.assert_kumascript(
            '{{cssxref("-moz-border-image")}}', 'cssxref',
            ['-moz-border-image'])

    def test_kumascript_one_arg_no_quotes(self):
        self.assert_kumascript(
            '{{CompatGeckoDesktop(27)}}', 'CompatGeckoDesktop', ['27'])

    def test_kumascript_three_args(self):
        self.assert_kumascript(
            ("{{SpecName('CSS3 Backgrounds', '#the-background-size',"
             " 'background-size')}}"),
            "SpecName",
            ["CSS3 Backgrounds", "#the-background-size",
             "background-size"])

    def assert_th(self, th, expected):
        parsed = page_grammar['th_elem'].parse(th)
        self.assertEqual(expected, self.visitor.visit(parsed))
        self.assertEqual([], self.visitor.issues)

    def test_th_elem_simple(self):
        th = '<th>Simple</th>'
        expected = {
            'type': 'th', 'start': 0, 'end': 4, 'attributes': {},
            'content': {'start': 4, 'end': 10, 'text': 'Simple'}}
        self.assert_th(th, expected)

    def test_th_elem_eat_whitespace(self):
        th = '<th> Eats Whitespace </th>'
        expected = {
            'type': 'th', 'start': 0, 'end': 4, 'attributes': {},
            'content': {'start': 5, 'end': 21, 'text': 'Eats Whitespace'}}
        self.assert_th(th, expected)

    def test_th_elem_attrs(self):
        th = '<th scope="col">Col Scope</th>'
        expected = {
            'type': 'th', 'start': 0, 'end': 16,
            'attributes': {'scope': {'start': 4, 'end': 15, 'value': 'col'}},
            'content': {'start': 16, 'end': 25, 'text': 'Col Scope'}}
        self.assert_th(th, expected)

    def test_th_elem_in_strong(self):
        th = '<th><strong>Strong</strong></th>'
        expected = {
            'type': 'th', 'start': 0, 'end': 4, 'attributes': {},
            'content': {
                'start': 12, 'end': 18, 'text': 'Strong', 'strong': True}}
        self.assert_th(th, expected)

    def test_cleanup_whitespace(self):
        text = """ This
        text <br/>
        has\t lots\xa0of
        extra&nbsp;whitespace.
        """
        expected = "This text has lots of extra whitespace."
        self.assertEqual(expected, self.visitor.cleanup_whitespace(text))

    def test_unquote_double(self):
        self.assertEqual('foo', self.visitor.unquote('"foo"'))

    def test_unquote_single(self):
        self.assertEqual('foo', self.visitor.unquote("'foo'"))

    def test_unquote_no_quote(self):
        self.assertEqual('27', self.visitor.unquote("27"))

    def test_unquote_unbalanced(self):
        self.assertRaises(ValueError, self.visitor.unquote, "'Mixed\"")

    def test_unquote_quote_plus_text(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/@viewport/max-zoom
        text = '"max-zoom" descriptor'
        self.assertEqual(text, self.visitor.unquote(text))

    def assert_kumascript_to_html(
            self, kumascript, expected_text, scope='specdesc', issues=None):
        parsed = page_grammar['kumascript'].parse('{{' + kumascript + '}}')
        item = self.visitor.visit(parsed)
        text = self.visitor.kumascript_to_html(item, scope)
        self.assertEqual(expected_text, text)
        self.assertEqual(self.visitor.issues, issues or [])

    def test_kumascript_to_html_xref_csslength(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/vertical-align
        self.assert_kumascript_to_html(
            'xref_csslength()', '<code>&lt;length&gt;</code>')

    def test_kumascript_to_html_xref_csspercentage(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/position_value
        self.assert_kumascript_to_html(
            'xref_csspercentage()', '<code>&lt;percentage&gt;</code>')

    def test_kumascript_to_html_xref_cssstring(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/attr
        self.assert_kumascript_to_html(
            'xref_cssstring()', '<code>&lt;string&gt;</code>')

    def test_kumascript_to_html_xref_cssimage(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/list-style-image
        self.assert_kumascript_to_html(
            'xref_cssimage()', '<code>&lt;image&gt;</code>')

    def test_kumascript_to_html_xref_csscolorvalue(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/background-color
        self.assert_kumascript_to_html(
            'xref_csscolorvalue()', '<code>&lt;color&gt;</code>')

    def test_kumascript_to_html_xref_cssvisual(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/break-after
        self.assert_kumascript_to_html('xref_cssvisual', '<code>visual</code>')

    def test_kumascript_to_html_cssxref(self):
        # https://developer.mozilla.org/en-US/docs/Web/CSS/vertical-align
        self.assert_kumascript_to_html(
            'cssxref("display")', '<code>display</code>')

    def test_kumascript_to_html_domxref_1arg(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/CharacterData
        self.assert_kumascript_to_html(
            'domxref("ChildNode")', '<code>ChildNode</code>')

    def test_kumascript_to_html_domxref_2arg(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent/initCustomEvent
        self.assert_kumascript_to_html(
            'domxref("CustomEvent.CustomEvent", "CustomEvent()")',
            '<code>CustomEvent()</code>')

    def test_kumascript_to_html_htmlelement(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/HTMLIsIndexElement
        self.assert_kumascript_to_html(
            'HTMLElement("isindex")', '<code>&lt;isindex&gt;</code>')

    def test_kumascript_to_html_htmlelement_with_space(self):
        # https://developer.mozilla.org/en-US/docs/Template:HTMLElement
        self.assert_kumascript_to_html(
            'HTMLElement("is index")', '<code>is index</code>')

    def test_kumascript_to_html_jsxref_1arg(self):
        # https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array
        self.assert_kumascript_to_html(
            'jsxref("Array.isArray")', '<code>Array.isArray</code>')

    def test_kumascript_to_html_jsxref_2arg(self):
        # https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/toString
        self.assert_kumascript_to_html(
            'jsxref("Global_Objects/null", "null")', '<code>null</code>')

    def test_kumascript_to_html_specname(self):
        # https://developer.mozilla.org/en-US/docs/Web/API/AbstractWorker
        self.assert_kumascript_to_html(
            'SpecName("Web Workers")', 'specification Web Workers')

    def test_kumascript_to_html_unknown_kumascript(self):
        issues = [
            ('unknown_kumascript', 0, 23,
             {'name': 'Unknown', 'args': ['textarea'],
              'scope': 'specdesc',
              'kumascript': '{{Unknown(textarea)}}'})]
        self.assert_kumascript_to_html(
            'Unknown("textarea")', None, issues=issues)

    def assert_join_content(self, content_bits, expected_text):
        text = self.visitor.join_content(content_bits)
        self.assertEqual(expected_text, text)

    def test_join_content_simple(self):
        content_bits = ['Works', 'like', 'join.']
        expected_text = 'Works like join.'
        self.assert_join_content(content_bits, expected_text)

    def assert_browser_lookup(self, name, browser_id, fixed_name, slug):
        lookup = self.visitor.browser_id_name_and_slug(name)
        self.assertEqual(browser_id, lookup[0])
        self.assertEqual(fixed_name, lookup[1])
        self.assertEqual(slug, lookup[2])

    def test_browser_lookup_not_found(self):
        self.assert_browser_lookup(
            'Firefox (Gecko)', '_Firefox (Gecko)', 'Firefox',
            '_Firefox (Gecko)')

    def test_browser_id_name_and_slug_found(self):
        firefox = self.get_instance(Browser, 'firefox')
        self.assert_browser_lookup(
            'Firefox (Gecko)', firefox.id, 'Firefox', 'firefox')

    def test_browser_id_name_and_slug_cached(self):
        self.assert_browser_lookup(
            'Firefox (Gecko)', '_Firefox (Gecko)', 'Firefox',
            '_Firefox (Gecko)')
        self.get_instance(Browser, 'firefox')
        self.assert_browser_lookup(
            'Firefox (Gecko)', '_Firefox (Gecko)', 'Firefox',
            '_Firefox (Gecko)')  # Still not found

    def assert_feature_lookup(self, name, feature_id, slug):
        lookup = self.visitor.feature_id_and_slug(name)
        self.assertEqual(feature_id, lookup[0])
        self.assertEqual(slug, lookup[1])

    def test_feature_id_and_slug_not_found(self):
        self.assert_feature_lookup(
            'Basic support', '_basic support',
            'web-css-background-size_basic_support')

    def test_feature_id_and_slug_found(self):
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')
        self.assert_feature_lookup(
            'Basic support', feature.id,
            'web-css-background-size-basic_support')

    def test_feature_id_and_slug_cached(self):
        self.assert_feature_lookup(
            'Basic support', '_basic support',
            'web-css-background-size_basic_support')
        self.get_instance(Feature, 'web-css-background-size-basic_support')
        self.assert_feature_lookup(
            'Basic support', '_basic support',
            'web-css-background-size_basic_support')  # Still not found

    def test_feature_id_and_slug_existing_slug(self):
        self.create(Feature, slug='web-css-background-size_basic_support')
        self.assert_feature_lookup(
            'Basic support', '_basic support',
            'web-css-background-size_basic_support1')


class TestScrape(TestCase):
    def setUp(self):
        self.feature = self.get_instance(Feature, 'web-css-background-size')

    def assertScrape(self, page, specs, issues):
        actual = scrape_page(page, self.feature)
        self.assertEqual(actual['locale'], 'en')
        self.assertDataEqual(actual['specs'], specs)
        self.assertDataEqual(actual['compat'], [])
        self.assertDataEqual(actual['footnotes'], None)
        self.assertDataEqual(actual['issues'], issues)

    def test_empty(self):
        page = ""
        self.assertScrape(page, [], [])

    def test_not_compat_page(self):
        page = "<h3>I'm not a compat page</h3>"
        self.assertScrape(page, [], [])

    def test_incomplete_parse_error(self):
        page = "<h2>Specifications</h2><p>Incomplete</p>"
        self.assertScrape(page, [], [('halt_import', 0, 40, {})])

    def test_spec_only(self):
        """Test with a only a Specification section."""
        spec = self.get_instance(Specification, 'css3_backgrounds')
        page = sample_spec_section
        specs = [{
            'specification.mdn_key': 'CSS3 Backgrounds',
            'specification.id': spec.id,
            'section.subpath': '#the-background-size',
            'section.name': 'background-size',
            'section.note': '',
            'section.id': None,
        }]
        self.assertScrape(page, specs, [])

    def test_doc_parse_error(self):
        # https://developer.mozilla.org/en-US/docs/Navigation_timing
        page = sample_compat_section.replace('h2', 'h3')
        self.assertScrape(page, [], [('doc_parse_error', 0, 57, {})])


class FeaturePageTestCase(TestCase):
    def setUp(self):
        path = "/en-US/docs/Web/CSS/background-size"
        url = "https://developer.mozilla.org" + path
        self.feature = self.get_instance(Feature, 'web-css-background-size')
        self.page = FeaturePage.objects.create(
            url=url, feature=self.feature, status=FeaturePage.STATUS_PARSING)
        meta = self.page.meta()
        meta.raw = dumps({
            'locale': 'en-US', 'url': path, 'title': 'background-size',
            'translations': [{
                'locale': 'fr',
                'url': path.replace('en-US', 'fr'),
                'title': 'background-size',
            }]})
        meta.status = meta.STATUS_FETCHED
        meta.save()

    def empty_scrape(self):
        return {
            'locale': 'en', 'specs': [], 'issues': [], 'errors': [],
            'compat': [], 'footnotes': None}

    def empty_view(self, scraped_data):
        return {
            'features': {
                'experimental': False,
                'id': str(self.feature.id),
                'links': {
                    'children': [],
                    'parent': str(self.feature.parent.id),
                    'sections': [],
                    'supports': []},
                'mdn_uri': {
                    'en': ('https://developer.mozilla.org/en-US/docs/'
                           'Web/CSS/background-size'),
                    'fr': ('https://developer.mozilla.org/fr/docs/'
                           'Web/CSS/background-size')},
                'name': 'background-size',
                'obsolete': False,
                'slug': 'web-css-background-size',
                'stable': True,
                'standardized': True,
            },
            'linked': {
                'browsers': [],
                'features': [],
                'maturities': [],
                'sections': [],
                'specifications': [],
                'supports': [],
                'versions': [],
            },
            'meta': {
                'compat_table': {
                    'languages': ['en', 'fr'],
                    'notes': {},
                    'pagination': {},
                    'supports': {str(self.feature.id): {}},
                    'tabs': []
                },
                'scrape': {
                    'phase': 'Starting Import',
                    'issues': [],
                    'raw': scraped_data}}}


class TestScrapedViewFeature(FeaturePageTestCase):
    def test_empty_scrape(self):
        scraped_data = self.empty_scrape()
        view = ScrapedViewFeature(self.page, scraped_data)
        out = view.generate_data()
        expected = self.empty_view(scraped_data)
        self.assertDataEqual(expected, out)

    def test_load_specification(self):
        spec = self.get_instance(Specification, 'css3_backgrounds')
        maturity = spec.maturity
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        spec_content, mat_content = view.load_specification(spec.id)
        expected_spec = {
            'id': str(spec.id), 'slug': spec.slug, 'mdn_key': spec.mdn_key,
            'uri': spec.uri, 'name': spec.name,
            'links': {'maturity': str(maturity.id), 'sections': []}}
        self.assertDataEqual(expected_spec, spec_content)
        expected_mat = {
            'id': str(maturity.id), 'slug': maturity.slug,
            'name': maturity.name}
        self.assertDataEqual(expected_mat, mat_content)

    def test_new_specification(self):
        spec_row = {
            'section.note': 'section note',
            'section.subpath': '#section',
            'section.name': 'section',
            'specification.mdn_key': 'CSS3 UI',
            'section.id': None,
            'specification.id': None}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        spec_content, mat_content = view.new_specification(spec_row)
        expected_spec = {
            'id': '_CSS3 UI', 'mdn_key': 'CSS3 UI',
            'links': {'maturity': '_unknown', 'sections': []}}
        self.assertDataEqual(expected_spec, spec_content)
        expected_mat = {
            'id': '_unknown', 'slug': '', 'name': {'en': 'Unknown'},
            'links': {'specifications': []}}
        self.assertDataEqual(expected_mat, mat_content)

    def test_load_section(self):
        section = self.get_instance(Section, 'background-size')
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        section_content = view.load_section(section.id)
        expected = {
            'id': str(section.id),
            'name': section.name, 'note': {},
            'number': None, 'subpath': section.subpath,
            'links': {'specification': str(section.specification.id)}}
        self.assertDataEqual(expected, section_content)

    def test_new_section(self):
        spec_row = {
            'section.note': 'section note',
            'section.subpath': '#section',
            'section.name': 'section',
            'specification.mdn_key': 'CSS3 UI',
            'section.id': None,
            'specification.id': None}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        section_content = view.new_section(spec_row, '_CSS3_UI')
        expected = {
            'id': '_CSS3_UI_#section',
            'name': {'en': 'section'}, 'note': {'en': 'section note'},
            'number': None, 'subpath': {'en': '#section'},
            'links': {'specification': '_CSS3_UI'}}
        self.assertDataEqual(expected, section_content)

    def test_load_browser(self):
        browser = self.get_instance(Browser, 'firefox')
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        browser_content = view.load_browser(browser.id)
        expected = {
            'id': str(browser.id), 'name': {'en': 'Firefox'}, 'note': None,
            'slug': browser.slug}
        self.assertDataEqual(expected, browser_content)

    def test_new_browser(self):
        browser_entry = {
            'id': '_Firefox (Gecko)', 'name': 'Firefox',
            'slug': '_Firefox (Gecko)'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        browser_content = view.new_browser(browser_entry)
        expected = {
            'id': '_Firefox (Gecko)', 'name': {'en': 'Firefox'}, 'note': None,
            'slug': ''}
        self.assertDataEqual(expected, browser_content)

    def test_load_version(self):
        version = self.get_instance(Version, ('firefox', '1.0'))
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        version_content = view.load_version(version.id)
        expected = {
            'id': str(version.id), 'version': '1.0', 'status': 'unknown',
            'note': None, 'release_day': None, 'retirement_day': None,
            'release_notes_uri': None, 'order': 0,
            'links': {'browser': str(version.browser_id)}}
        self.assertDataEqual(expected, version_content)

    def test_new_version(self):
        version_entry = {
            'id': '_version', 'browser': '_browser', 'version': '1.0'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        version_content = view.new_version(version_entry)
        expected = {
            'id': '_version', 'version': '1.0', 'status': 'unknown',
            'note': None, 'release_day': None, 'retirement_day': None,
            'release_notes_uri': None,
            'links': {'browser': '_browser'}}
        self.assertDataEqual(expected, version_content)

    def test_new_unnamed_current_version(self):
        version_entry = {
            'id': '_version', 'browser': '_browser', 'version': ""}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        version_content = view.new_version(version_entry)
        expected = {
            'id': '_version', 'version': 'current', 'status': 'current',
            'note': None, 'release_day': None, 'retirement_day': None,
            'release_notes_uri': None,
            'links': {'browser': '_browser'}}
        self.assertDataEqual(expected, version_content)

    def test_new_nightly_version(self):
        version_entry = {
            'id': '_version', 'browser': '_browser', 'version': 'nightly'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        version_content = view.new_version(version_entry)
        expected = {
            'id': '_version', 'version': 'nightly', 'status': 'future',
            'note': None, 'release_day': None, 'retirement_day': None,
            'release_notes_uri': None,
            'links': {'browser': '_browser'}}
        self.assertDataEqual(expected, version_content)

    def test_load_feature(self):
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        feature_content = view.load_feature(feature.id)
        expected = {
            'id': str(feature.id), 'name': {'en': 'Basic support'},
            'slug': feature.slug, 'mdn_uri': None, 'obsolete': False,
            'stable': True, 'standardized': True, 'experimental': False,
            'links': {
                'children': [], 'parent': str(self.feature.id),
                'sections': [], 'supports': []}}
        self.assertDataEqual(expected, feature_content)

    def test_load_feature_canonical_name(self):
        feature = self.create(
            Feature, slug='web-css-background-size_list-item',
            name={'zxx': 'list-item'}, parent=self.feature)
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        feature_content = view.load_feature(feature.id)
        expected = {
            'id': str(feature.id), 'name': 'list-item',
            'slug': feature.slug, 'mdn_uri': None, 'obsolete': False,
            'stable': True, 'standardized': True, 'experimental': False,
            'links': {
                'children': [], 'parent': str(self.feature.id),
                'sections': [], 'supports': []}}
        self.assertDataEqual(expected, feature_content)

    def test_new_feature(self):
        feature_entry = {
            'id': '_feature', 'name': 'Basic support',
            'slug': 'web-css-background-size_basic_support'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        feature_content = view.new_feature(feature_entry)
        expected = {
            'id': '_feature', 'name': {'en': 'Basic support'},
            'slug': 'web-css-background-size_basic_support',
            'mdn_uri': None, 'obsolete': False, 'stable': True,
            'standardized': True, 'experimental': False,
            'links': {
                'children': [], 'parent': str(self.feature.id),
                'sections': [], 'supports': []}}
        self.assertDataEqual(expected, feature_content)

    def test_new_feature_canonical(self):
        feature_entry = {
            'id': '_feature', 'name': 'cover', 'canonical': True,
            'slug': 'web-css-background-size_cover'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        feature_content = view.new_feature(feature_entry)
        expected = {
            'id': '_feature', 'name': 'cover',
            'slug': 'web-css-background-size_cover',
            'mdn_uri': None, 'obsolete': False, 'stable': True,
            'standardized': True, 'experimental': False,
            'links': {
                'children': [], 'parent': str(self.feature.id),
                'sections': [], 'supports': []}}
        self.assertDataEqual(expected, feature_content)

    def test_load_support(self):
        version = self.get_instance(Version, ('firefox', '1.0'))
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')
        support = self.create(Support, version=version, feature=feature)
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        support_content = view.load_support(support.id)
        expected = {
            'id': str(support.id), 'support': 'yes', 'note': None,
            'prefix': None, 'prefix_mandatory': False, 'protected': False,
            'requires_config': None, 'default_config': None,
            'alternate_name': None, 'alternate_mandatory': False,
            'links': {'feature': str(feature.id), 'version': str(version.id)}}
        self.assertDataEqual(expected, support_content)

    def test_new_support(self):
        support_entry = {
            'id': '_support', 'feature': '_feature', 'version': '_version',
            'support': 'yes'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        support_content = view.new_support(support_entry)
        expected = {
            'id': '_support', 'support': 'yes', 'note': None,
            'prefix': None, 'prefix_mandatory': False, 'protected': False,
            'requires_config': None, 'default_config': None,
            'alternate_name': None, 'alternate_mandatory': False,
            'links': {'feature': '_feature', 'version': '_version'}}
        self.assertDataEqual(expected, support_content)

    def test_new_support_with_note(self):
        support_entry = {
            'id': '_support', 'feature': '_feature', 'version': '_version',
            'support': 'yes', 'footnote': 'The Footnote'}
        view = ScrapedViewFeature(self.page, self.empty_scrape())
        support_content = view.new_support(support_entry)
        expected = {
            'id': '_support', 'support': 'yes', 'note': {'en': 'The Footnote'},
            'prefix': None, 'prefix_mandatory': False, 'protected': False,
            'requires_config': None, 'default_config': None,
            'alternate_name': None, 'alternate_mandatory': False,
            'links': {'feature': '_feature', 'version': '_version'}}
        self.assertDataEqual(expected, support_content)

    def test_load_specification_row_new_resources(self):
        scraped_data = self.empty_scrape()
        scraped_spec = {
            'section.note': 'section note',
            'section.subpath': '#section',
            'section.name': 'section',
            'specification.mdn_key': 'CSS3 UI',
            'section.id': None,
            'specification.id': None}
        scraped_data['specs'].append(scraped_spec)
        view = ScrapedViewFeature(self.page, scraped_data)
        out = view.generate_data()
        spec_content, mat_content = view.new_specification(scraped_spec)
        section_content = view.new_section(scraped_spec, spec_content['id'])
        expected = self.empty_view(scraped_data)
        expected['features']['links']['sections'] = [section_content['id']]
        expected['linked']['maturities'] = [mat_content]
        expected['linked']['specifications'] = [spec_content]
        expected['linked']['sections'] = [section_content]
        self.assertDataEqual(expected, out)

    def test_load_specification_row_existing_resources(self):
        section = self.get_instance(Section, 'background-size')
        spec = section.specification
        scraped_spec = {
            'section.note': 'new note',
            'section.subpath': section.subpath['en'],
            'section.name': section.name['en'],
            'specification.mdn_key': spec.mdn_key,
            'section.id': section.id,
            'specification.id': spec.id}
        scraped_data = self.empty_scrape()
        scraped_data['specs'].append(scraped_spec)
        view = ScrapedViewFeature(self.page, scraped_data)
        out = view.generate_data()
        expected = self.empty_view(scraped_data)
        spec_content, mat_content = view.load_specification(spec.id)
        section_content = view.load_section(section.id)
        section_content['note'] = {'en': 'new note'}
        expected['features']['links']['sections'] = [str(section.id)]
        expected['linked']['maturities'] = [mat_content]
        expected['linked']['specifications'] = [spec_content]
        expected['linked']['sections'] = [section_content]
        self.assertDataEqual(expected, out)

    def test_load_compat_table_new_resources(self):
        browser_id = '_Firefox (Gecko)'
        version_id = '_Firefox-1.0'
        feature_id = '_basic_support'
        support_id = '_%s-%s' % (feature_id, version_id)
        scraped_data = self.empty_scrape()
        scraped_table = {
            'name': 'desktop',
            'browsers': [{
                'id': browser_id, 'name': 'Firefox',
                'slug': '_Firefox (Gecko)'}],
            'versions': [{
                'id': version_id, 'browser': browser_id, 'version': '1.0'}],
            'features': [{
                'id': feature_id, 'name': 'Basic support',
                'slug': 'web-css-background-size_basic_support'}],
            'supports': [{
                'id': support_id, 'feature': feature_id, 'version': version_id,
                'support': 'yes'}]}
        scraped_data['compat'].append(scraped_table)
        view = ScrapedViewFeature(self.page, scraped_data)
        out = view.generate_data()
        browser_content = view.new_browser(scraped_table['browsers'][0])
        version_content = view.new_version(scraped_table['versions'][0])
        feature_content = view.new_feature(scraped_table['features'][0])
        support_content = view.new_support(scraped_table['supports'][0])
        expected = self.empty_view(scraped_data)
        expected['linked']['browsers'].append(browser_content)
        expected['linked']['versions'].append(version_content)
        expected['linked']['features'].append(feature_content)
        expected['linked']['supports'].append(support_content)
        expected['meta']['compat_table']['supports'][feature_id] = {
            browser_id: [support_id]}
        expected['meta']['compat_table']['tabs'].append({
            'name': {'en': 'Desktop Browsers'}, 'browsers': [browser_id]})
        self.assertDataEqual(expected, out)

    def test_load_compat_table_existing_resources(self):
        version = self.get_instance(Version, ('firefox', '1.0'))
        browser = version.browser
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')
        support = self.create(Support, version=version, feature=feature)
        browser_id = str(browser.id)
        version_id = str(version.id)
        feature_id = str(feature.id)
        support_id = str(support.id)
        scraped_data = self.empty_scrape()
        scraped_table = {
            'name': 'desktop',
            'browsers': [{
                'id': browser_id, 'name': browser.name['en'],
                'slug': browser.slug}],
            'versions': [{
                'id': version_id, 'browser': browser_id, 'version': '1.0'}],
            'features': [{
                'id': feature_id, 'name': feature.name['en'],
                'slug': feature.slug}],
            'supports': [{
                'id': support_id, 'feature': feature_id, 'version': version_id,
                'support': 'yes'}]}
        scraped_data['compat'].append(scraped_table)
        view = ScrapedViewFeature(self.page, scraped_data)
        out = view.generate_data()
        expected = self.empty_view(scraped_data)
        expected['linked']['browsers'].append(view.load_browser(browser.id))
        expected['linked']['versions'].append(view.load_version(version.id))
        expected['linked']['features'].append(view.load_feature(feature.id))
        expected['linked']['supports'].append(view.load_support(support.id))
        expected['meta']['compat_table']['supports'][feature_id] = {
            browser_id: [support_id]}
        expected['meta']['compat_table']['tabs'].append({
            'name': {'en': 'Desktop Browsers'},
            'browsers': [browser_id]})
        self.assertDataEqual(expected, out)

    def test_load_compat_table_new_support_with_note(self):
        version = self.get_instance(Version, ('firefox', '1.0'))
        browser = version.browser
        feature = self.get_instance(
            Feature, 'web-css-background-size-basic_support')
        browser_id = str(browser.id)
        version_id = str(version.id)
        feature_id = str(feature.id)
        support_id = '_%s-%s' % (feature_id, version_id)
        scraped_data = self.empty_scrape()
        scraped_table = {
            'name': 'desktop',
            'browsers': [{
                'id': browser_id, 'name': browser.name['en'],
                'slug': browser.slug}],
            'versions': [{
                'id': version_id, 'browser': browser_id, 'version': '1.0'}],
            'features': [{
                'id': feature_id, 'name': feature.name['en'],
                'slug': feature.slug}],
            'supports': [{
                'id': support_id, 'feature': feature_id, 'version': version_id,
                'support': 'yes', 'footnote': 'Footnote'}]}
        scraped_data['compat'].append(scraped_table)
        view = ScrapedViewFeature(self.page, scraped_data)
        out = view.generate_data()
        expected = self.empty_view(scraped_data)
        support_content = view.new_support(scraped_table['supports'][0])
        expected['linked']['browsers'].append(view.load_browser(browser.id))
        expected['linked']['versions'].append(view.load_version(version.id))
        expected['linked']['features'].append(view.load_feature(feature.id))
        expected['linked']['supports'].append(support_content)
        expected['meta']['compat_table']['supports'][feature_id] = {
            browser_id: [support_id]}
        expected['meta']['compat_table']['tabs'].append({
            'name': {'en': 'Desktop Browsers'},
            'browsers': [browser_id]})
        expected['meta']['compat_table']['notes'][support_id] = 1
        self.assertDataEqual(expected, out)


class TestScrapeFeaturePage(FeaturePageTestCase):
    def set_content(self, content):
        for translation in self.page.translations():
            translation.status = translation.STATUS_FETCHED
            translation.raw = content
            translation.save()

    def test_empty_page(self):
        self.set_content('  ')
        scrape_feature_page(self.page)
        fp = FeaturePage.objects.get(id=self.page.id)
        self.assertEqual(fp.STATUS_NO_DATA, fp.status)
        self.assertEqual(
            [], fp.data['meta']['scrape']['raw']['issues'])
        self.assertFalse(fp.has_issues)

    def test_parse_issue(self):
        bad_page = '''\
<p>The page has a bad specification section.</p>
<h2 id="Specifications">Specifications</h2>
<p>No specs</p>
'''
        self.set_content(bad_page)
        scrape_feature_page(self.page)
        fp = FeaturePage.objects.get(id=self.page.id)
        self.assertEqual(fp.STATUS_PARSED, fp.status)
        expected_issues = [[
            'section_skipped', 96, 108,
            {'title': 'Specifications', 'rule_name': 'whynospec_start',
             'rule': ('whynospec_start = ks_esc_start "WhyNoSpecStart" _'
                      ' ks_esc_end _')}]]
        self.assertEqual(
            expected_issues,
            fp.data['meta']['scrape']['raw']['issues'])
        self.assertTrue(fp.has_issues)


class TestDateToIso(TestCase):
    def test_date(self):
        self.assertEqual('2015-02-02', date_to_iso(date(2015, 2, 2)))

    def test_none(self):
        self.assertEqual(None, date_to_iso(''))
