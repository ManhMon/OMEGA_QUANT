from vnstock import Reference
ref = Reference()
m = ref.market()
print(f"Market.symbol methods: {[x for x in dir(m.symbol) if not x.startswith('_')]}")
