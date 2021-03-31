import setuptools

setuptools.setup(
    name='test',
    extras_require=dict(tests=['pytest']),
    packages=setuptools.find_packages(where='src'),
    package_dir={'': 'src', }
)
