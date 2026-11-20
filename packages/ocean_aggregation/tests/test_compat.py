import unittest
from unittest.mock import Mock

from soup.core.contracts import ValidationError
from soup_pkg_ocean_aggregation.compat import configuration, knowledge, require_no_classes


class OceanCompatibilityTests(unittest.TestCase):
    def test_configuration_restores_state_after_an_error(self):
        previous = (knowledge.log, knowledge.ekg, knowledge.entities)
        log, ekg = object(), object()

        with self.assertRaisesRegex(RuntimeError, "aggregation failed"):
            with configuration(log, ekg):
                self.assertIs(knowledge.log, log)
                self.assertIs(knowledge.ekg, ekg)
                self.assertEqual(knowledge.entities, set())
                raise RuntimeError("aggregation failed")

        self.assertIs(knowledge.log, previous[0])
        self.assertIs(knowledge.ekg, previous[1])
        self.assertIs(knowledge.entities, previous[2])

    def test_rejects_memgraph_state_with_existing_classes(self):
        database = Mock()
        database.execute.return_value = [{"classes": 0}]
        require_no_classes(database)

        database.execute.return_value = [{"classes": 1}]
        with self.assertRaisesRegex(ValidationError, "already contains Class nodes"):
            require_no_classes(database)
