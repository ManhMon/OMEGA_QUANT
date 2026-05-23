from vnstock import Reference
ref = Reference()
m = ref.market()
print(f"Market methods: {[x for x in dir(m) if not x.startswith('_')]}")
