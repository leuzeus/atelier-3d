import unittest
from unittest.mock import patch
from a3d.core import StudioError
from a3d.tools import TOOLS,call


class PatternEaseTool(unittest.TestCase):
    def test_invalid_or_bypass_arguments_fail_before_project_access(self):
        arguments={'project_root':'missing','compiled_dossier_path':'compiled.json',
                   'design_decision_path':'decision.json','policy_path':'policy.json','output_dir':'variants/new'}
        for changed in ({key:value for key,value in arguments.items()if key!='design_decision_path'},
                        dict(arguments,force_approval=True),dict(arguments,output_dir='')):
            with self.subTest(arguments=changed),patch('a3d.tools.Project')as project,self.assertRaises(StudioError):
                call('studio_prepare_pattern_ease_variant',changed)
            project.assert_not_called()

    def test_descriptor_reports_filesystem_mutation_without_native_or_external_execution(self):
        descriptor=TOOLS['studio_prepare_pattern_ease_variant']['descriptor']
        self.assertFalse(descriptor['annotations']['readOnlyHint'])
        self.assertFalse(descriptor['annotations']['destructiveHint'])
        self.assertFalse(descriptor['annotations']['openWorldHint'])
        self.assertNotIn('approved',descriptor['inputSchema']['properties'])

    def test_facade_passes_exact_design_inputs_to_variant_service(self):
        arguments={'project_root':'source-project','compiled_dossier_path':'compiled.json',
                   'design_decision_path':'decision.json','policy_path':'policy.json','output_dir':'variants/new'}
        expected={'status':'PATTERN_VARIANT_REQUIRES_REVIEW','fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED'}
        with patch('a3d.tools.Project')as project,patch('a3d.pattern_ease_variant.prepare_project_pattern_ease_variant',return_value=expected)as service:
            self.assertEqual(call('studio_prepare_pattern_ease_variant',arguments),expected)
        service.assert_called_once_with(project.return_value,'compiled.json','decision.json','policy.json','variants/new')


if __name__=='__main__':unittest.main()
