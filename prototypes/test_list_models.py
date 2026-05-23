from omega.data.registry import ModelRegistry
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    reg = ModelRegistry(registry_path=tmp)
    reg.register_model('test', {}, {
        'trained_at': '2026-05-14T00:00:00Z',
        'available_at': '2026-05-14T01:00:00Z',
        'train_end_date': '2026-05-13',
        'validation_start_date': '2026-05-14'
    })
    models = reg.list_models()
    print('Type:', type(models))
    if models:
        print('First item keys:', list(models[0].keys()) if isinstance(models[0], dict) else 'Not a dict')
        print('First item:', models[0])
