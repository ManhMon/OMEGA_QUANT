import time
import sys
import gc

def measure_imports():
    # Cold import measurement
    t0 = time.perf_counter()
    import omega.quant.ultimate_alpha_arsenal as uaa
    t1 = time.perf_counter()
    cold_time = t1 - t0
    
    # Warm import
    t0 = time.perf_counter()
    import omega.quant.ultimate_alpha_arsenal as uaa2
    t1 = time.perf_counter()
    warm_time = t1 - t0
    
    print(f"COLD_IMPORT_TIME: {cold_time:.4f}s")
    print(f"WARM_IMPORT_TIME: {warm_time:.4f}s")

if __name__ == "__main__":
    measure_imports()
