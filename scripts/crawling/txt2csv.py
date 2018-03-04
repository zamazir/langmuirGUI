import pandas as pd

df = pd.read_csv("tdiv_results_analysed.txt", delimiter=r"\s*", engine='python')
df.columns = ['shotnr', 'tdiv_mean', 'useful']
df['tdiv_mean'] = df['tdiv_mean'].astype(float)
df = df[df['useful'] == 'useful']
df = df[df['tdiv_mean'] <= 0]
df = df.sort_values('tdiv_mean')

df.to_csv("tdiv_filtered.csv")
