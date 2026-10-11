"""Offline: records beyond #10 are passed to Storage+DB deletion."""
import asyncio
from unittest.mock import AsyncMock, patch

import history_store

UID = '11111111-1111-4111-8111-111111111111'


def test_latest_10_trim_and_delete_oldest():
    ordered_rows = [{'id': f'{i:08d}-1111-4111-8111-111111111111', 'created_at': f'{25-i:02d}'}
                    for i in range(12)]
    deleter = AsyncMock()
    with patch('history_store._rows', new=AsyncMock(return_value=ordered_rows)), \
         patch('history_store._delete_row', new=deleter):
        count = asyncio.run(history_store._trim(object(), UID))
    assert count == 2
    assert [item.args[2]['id'] for item in deleter.await_args_list] == [ordered_rows[10]['id'], ordered_rows[11]['id']]


def test_delete_removes_objects_before_record():
    events = []
    async def removed(client, paths):
        events.append(('objects', paths))
    async def query(client, path, method='GET', **kwargs):
        events.append(('row', method, kwargs['params']['user_id']))
    row = {'id': 'xyz', 'image_path': f'{UID}/xyz/original.webp',
           'overlay_path': f'{UID}/xyz/overlay.webp', 'mask_path': None}
    with patch('history_store._remove_objects', new=removed), patch('history_store._query', new=query):
        asyncio.run(history_store._delete_row(object(), UID, row))
    assert events[0][0] == 'objects'
    assert events[1] == ('row', 'DELETE', f'eq.{UID}')
