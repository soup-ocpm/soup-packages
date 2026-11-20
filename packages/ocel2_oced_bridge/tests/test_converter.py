"""Focused checks using SOUP's real contracts; run with PYTHONPATH=soup-server."""
from __future__ import annotations

import base64
import csv
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ocel2_oced_bridge.server.model import parse
from ocel2_oced_bridge.server.converter import convert
from soup.core.contracts import ValidationError


def document():
    return {
        'eventTypes':[{'name':'Purchase','attributes':[{'name':'ok','type':'boolean'}]}],
        'objectTypes':[{'name':'Order item','attributes':[{'name':'cost','type':'float'}]},{'name':'Customer','attributes':[]}],
        'events':[{'id':'e,1','type':'Purchase','time':'2026-01-01T00:00:00.123456789Z','attributes':[{'name':'ok','value':False}],
                   'relationships':[{'objectId':'i 1','qualifier':'primary'},{'objectId':'i2','qualifier':'secondary'},{'objectId':'c1','qualifier':'client'}]}],
        'objects':[{'id':'i 1','type':'Order item','attributes':[{'name':'cost','time':'2020-01-01T00:00:00Z','value':12.5}]},
                   {'id':'i2','type':'Order item','attributes':[]},{'id':'c1','type':'Customer','attributes':[]}],
    }


class ConverterTests(unittest.TestCase):
    def test_multiple_objects_types_and_missing_values(self):
        upload, options, summary = convert(parse(json.dumps(document()).encode()))
        rows=list(csv.DictReader(io.StringIO(upload.read().decode())))
        self.assertEqual(rows[0]['obj_Order_item'],'i 1,i2')
        self.assertEqual(rows[0]['obj_Customer'],'c1')
        self.assertEqual(rows[0]['id'],'e,1')
        self.assertEqual(rows[0]['attr_ok'],'false')
        self.assertEqual(rows[0]['eventDatetime'],'2026-01-01T00:00:00.123456789Z')
        self.assertEqual(options['events']['attr_types']['attr_ok'],'Boolean')
        objects=options['entities']['obj_Order_item']
        self.assertEqual(objects['attr_types']['attr_cost'],'Float')
        values=list(csv.DictReader(io.StringIO(base64.b64decode(objects['file']['base64']).decode())))
        self.assertEqual(values[0]['attr_cost'],'12.5')
        self.assertEqual(values[1]['attr_cost'],'')
        self.assertEqual(summary['qualifier_relationships_not_preserved'],3)

    def test_history_uses_chronological_not_lexical_order(self):
        raw=document()
        raw['objects'][0]['attributes']=[
            {'name':'cost','time':'2026-01-01T00:00:00Z','value':20.0},
            {'name':'cost','time':'2026-01-01T01:00:00+02:00','value':10.0},
        ]
        _,options,summary=convert(parse(json.dumps(raw).encode()))
        data=base64.b64decode(options['entities']['obj_Order_item']['file']['base64'])
        rows=list(csv.DictReader(io.StringIO(data.decode())))
        self.assertEqual(rows[0]['attr_cost'],'10.0')
        self.assertEqual(summary['additional_timed_object_attribute_values_not_preserved'],1)

    def test_unsupported_reference_identifier_is_rejected(self):
        raw=document();raw['objects'][0]['id']='bad,id'
        raw['events'][0]['relationships'][0]['objectId']='bad,id'
        with self.assertRaisesRegex(ValidationError,'cannot represent'):
            convert(parse(json.dumps(raw).encode()))

    def test_colliding_type_and_attribute_names_remain_distinct(self):
        raw=document();raw['objectTypes'].append({'name':'Order-item','attributes':[]})
        _,_,summary=convert(parse(json.dumps(raw).encode()))
        self.assertNotEqual(summary['object_type_columns']['Order item'],summary['object_type_columns']['Order-item'])


if __name__ == '__main__':
    unittest.main()
