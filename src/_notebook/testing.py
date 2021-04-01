from src.instruments.light_meter import LightMeasurement

measurements = [
    LightMeasurement(x=0.357075572013855, y=0.3628235161304474, fcd=2496.29931640625, CCT=4618.0,
                     duv=0.0012575466423404204),
    LightMeasurement(x=0.35707491636276245, y=0.36285483837127686, fcd=2496.173828125, CCT=4618.0,
                     duv=0.0012765390941315011),
    LightMeasurement(x=0.3570382595062256, y=0.3628543019294739, fcd=2495.87255859375, CCT=4619.0,
                     duv=0.0012918237945262925),
]

print(LightMeasurement.averaged_from(measurements))
