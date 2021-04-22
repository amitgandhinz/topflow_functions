#!/usr/bin/env python

import yaml

with open(".env.yaml", 'r') as stream:
    try:
        vars = yaml.safe_load(stream)

        for v in vars:
            print ("export " + v + "=" + vars[v])

    except yaml.YAMLError as exc:
        print(exc)