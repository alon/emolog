import pandas

import sys

pd = pandas.read_csv(sys.argv[-1])

for col in pd.columns:
  print("**** {:10} ****".format(col))
  print(pd[col].describe())
  print(pd[col].diff().describe())
