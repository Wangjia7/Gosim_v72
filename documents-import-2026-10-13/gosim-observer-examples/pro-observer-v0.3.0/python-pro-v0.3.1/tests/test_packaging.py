import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pack_agent

class PackagingContract(unittest.TestCase):
    def _manifest(self,environment):
        return {'schema_version':'observer-project-v1','protocol':'jsonl-v4','image':'python:3.12-slim','run':['python3','-u','agent.py'],'working_directory':'.','environment':environment}
    def test_accepts_32_settings_rejects_33_and_non_object(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'project';root.mkdir();out=Path(d)/'agent.zip'
            (root/'agent.py').write_text('pass\n')
            for env,valid in (({f'K{i}':'1' for i in range(32)},True),({f'K{i}':'1' for i in range(33)},False),([],False),({'K':1},False)):
                if out.exists():out.unlink()
                (root/'observer.project.json').write_text(json.dumps(self._manifest(env)))
                with patch.object(pack_agent,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                    if valid:self.assertEqual(pack_agent.main(['--out',str(out)]),0)
                    else:
                        with self.assertRaises(SystemExit):pack_agent.main(['--out',str(out)])
                self.assertEqual(out.exists(),valid)
