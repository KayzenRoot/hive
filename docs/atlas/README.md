# HIVE maintenance maps

The Code Atlas, Module Registry, and Test Map are deterministic generated
indexes for future maintenance. Regenerate them with:

~~~bash
python scripts/generate_maps.py
~~~

Check that committed maps are current with:

~~~bash
python scripts/generate_maps.py --check
~~~
