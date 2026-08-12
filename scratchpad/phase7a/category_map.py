import json
from apps.catalog.models import Product
ids = [257, 307, 667, 1110, 1111, 1817, 1855, 6213, 6681, 6682, 10537, 10631, 10632, 12957, 12959, 13936, 22473, 22650, 22651, 23255, 26863, 26864, 26865, 27250, 27251, 27254, 28677, 28891, 28892, 28893, 28901, 30223, 30225, 30870, 31106, 31109, 32022, 32027, 32407, 32688, 34428, 35076, 36300, 36302, 36304, 36377, 36378, 36713, 37269, 37270, 37594, 38350, 39427, 42094]
rows = {str(p.pk): [p.category_id, p.category.name if p.category else ''] for p in Product.objects.filter(pk__in=ids).select_related('category')}
print(json.dumps(rows, ensure_ascii=False, sort_keys=True))
