"""Menu and version-state tests using isolated synthetic data only."""
from unittest.mock import patch
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from studio.library_page import LibraryPage
from studio.model import StudioProject, EditorNote
from studio.i18n import tr


def test_versions_status_and_context_commands(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = LibraryPage(lambda: StudioProject(), root=tmp_path/'library')
    try:
        assert not page.command_buttons['library.open'].isEnabled()
        assert not page.export_button.isEnabled()
        for text in ('', 'Hello'):
            page.library.add_project(StudioProject(title='Song',artist='Test',
                notes=[EditorNote(1,.5,60,text)]))
        page.refresh()
        assert page.projects.topLevelItemCount() == 2
        statuses = {page.projects.topLevelItem(i).text(3) for i in range(2)}
        assert statuses == {tr('library.draft'), tr('library.needs_media')}
        assert all(page.projects.topLevelItem(i).text(2) != '-' for i in range(2))
        page.projects.topLevelItem(0).setSelected(True)
        assert page.command_buttons['library.open'].isEnabled()
        assert page.command_buttons['library.community_upload'].isEnabled()
        assert not page.command_buttons['usb.title'].isEnabled()
        page.tabs.setCurrentWidget(page.packages)
        assert not page.command_buttons['library.open'].isEnabled()
        assert not page.command_buttons['library.community_upload'].isEnabled()
    finally:
        page.close()
        app.processEvents()


def test_usb_catalog_display_and_whole_pack_confirmation(tmp_path):
    from studio.usb_dialog import UsbDialog
    from studio.usb_catalog import UsbPackage
    app = QApplication.instance() or QApplication([])
    with patch('studio.usb_dialog.xbox_volumes', return_value=[]):
        dialog = UsbDialog(browse=True)
        try:
            entry = UsbPackage(tmp_path/'ABCD', 'Friendly pack',
                [dict(artist='Artist',title='Song')], '2026-10-09T10:00:00+00:00',
                'utc', 'CID', 0, (1024,0,0,''), local='newer')
            dialog.show_contents([entry])
            row = dialog.contents.topLevelItem(0)
            assert row.text(0) == 'Friendly pack'
            assert row.child(0).text(0) == 'Artist - Song'
            assert row.text(3) == tr('usb.local_newer')
            assert not dialog.remove_button.isEnabled()
            assert dialog.tabs.currentIndex() == 0
            assert row.data(0, Qt.ItemDataRole.UserRole).path == entry.path
        finally:
            dialog.close()
            app.processEvents()
