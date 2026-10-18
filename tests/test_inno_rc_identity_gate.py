"""Prevent the 0.2 installer from replacing the public beta or development RC."""
from __future__ import annotations

from pathlib import Path
import re

ISS = Path(__file__).resolve().parents[1] / 'packaging/OCRYON.iss'
PUBLIC_BETA_APP_ID = '7F17E5CF-2330-4F34-9D6A-71834D9AD3F4'


def test_rc_inno_product_identity_does_not_collide_with_public_beta():
    source = ISS.read_text(encoding='utf-8')
    app_id = re.search(r'(?m)^AppId=\{\{([0-9A-Fa-f-]{36})\}\s*$', source)
    assert app_id is not None
    assert app_id.group(1).upper() != PUBLIC_BETA_APP_ID
    assert app_id.group(1).upper() != 'ABDD822D-3437-5C3D-A322-7AE362646840'
    assert '#define MyAppVersion "0.2.0"' in source
    assert r'DefaultDirName={localappdata}\Programs\OCRYON-0.2' in source
    assert 'UninstallDisplayName=OCRYON 0.2' in source
    assert r'Name: "{group}\OCRYON"' in source
    assert r'Name: "{userdesktop}\OCRYON"' in source
