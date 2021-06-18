#!/usr/bin/env python

import yaml

with open(".env.yaml", 'r') as stream:
    try:
        vars = yaml.safe_load(stream)

        print ("----------------------------------");
        for v in vars:
            print ("export " + v + "='" + str(vars[v]) + "'")

        print ("----------------------------------");

    except yaml.YAMLError as exc:
        print(exc)