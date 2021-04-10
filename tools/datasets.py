from rdflib import Dataset, URIRef, Literal, Namespace
import pickle

d = Dataset(default_union=True).parse("../data/items.trig", format="trig")
d.default_union = True
print(len(d))
# clean up HTTP/HTTPS for linked.data.gov.au
for s, p, o in d.triples((None, None, None)):
    #if "http://linked.data.gov.au" in str(s):
        print(s)
