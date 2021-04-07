import httpx
import asyncio
import pathlib
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DCAT, DCTERMS, DC, PROF, XSD, SDO
from itertools import chain

REG = Namespace("http://purl.org/linked-data/registry#")
IRG = Namespace("https://linked.data.gov.au/def/irg#")
LOCI = Namespace("http://linked.data.gov.au/def/loci#")
LOCIS = Namespace("https://linked.data.gov.au/def/loci#")
DCATS = Namespace("https://www.w3.org/ns/dcat#")

PREFIXES = {
    "rdfs": RDFS,
    "owl": OWL,
    "skos": SKOS,
    "dcat": DCAT,
    "dcats": "https://www.w3.org/ns/dcat#",
    "prof": PROF,
    "dcterms": DCTERMS,
    "dc": DC,
    "reg": REG,
    "irg": IRG,
    "loci": "http://linked.data.gov.au/def/loci#",
    "sdo": SDO
}


async def get_many(urls, headers=None):
    """Get RDF for all given IRIs
    """
    async def get_async(url):
        try:
            async with httpx.AsyncClient() as client:
                return await client.get(url, headers=headers)
        except Exception as e:
            print(url)
            print(e)
            return httpx.Response(status_code=500)

    resps = await asyncio.gather(*map(get_async, urls))
    return tuple(zip(urls, resps))


def download_rdf(urls):
    """Only get 200 results"""
    results = asyncio.run(get_many(urls, headers={"Accept": "text/turtle"}))

    pathlib.Path('catalogue').mkdir(parents=True, exist_ok=True)
    for result in [(r[0], r[1].text, r[1].url) for r in results if r[1].status_code == 200]:
        open("catalogue/{}.ttl".format(result[0].replace("https://linked.data.gov.au/", "").replace("/", "-")), "w").write(result[1])
    print("complete")


def check_rdf(dir):
    p = pathlib.Path(dir)
    cat = Graph()
    for f in p.iterdir():
        if f.name.endswith(".ttl"):
            try:
                print(str(f.name))
                g = Graph().parse(str(f), format="ttl")
            except Exception as e:
                print("{} not parsable Turtle".format(f))

                # pathlib.Path.unlink(f)
            cat += get_dcat(g)
    print("serialize")
    for k, v in PREFIXES.items():
        cat.bind(k, v)
    cat.serialize(destination="catalogue.ttl", format="ttl")


def get_dcat(g: Graph):
    # prefixes_str = ""
    # for k, v in prefixes:
    #     prefixes_str += "PREFIX {}: <{}>".format(k, v)

    # # title
    # q_title = """
    #     SELECT ?r ?label
    #     WHERE {
    #         {
    #             SELECT ?t
    #             WHERE {
    #                 VALUES ?t {
    #                     owl:Ontology
    #                     skos:ConceptScheme
    #                     dcat:Dataset
    #                     dcats:Dataset
    #                     reg:Register
    #                     irg:IRIRegister
    #                     prof:Profile
    #                     loci:Linkset
    #                 }
    #                 ?r a ?t .
    #             }
    #             LIMIT 1
    #         }
    #         VALUES ?lt {
    #             skos:prefLabel
    #             dc:title
    #             dcterms:title
    #             rdfs:label
    #         }
    #         ?r ?lt ?label .
    #     }
    #     LIMIT 1
    # """
    #
    # for r in g.query(q_title, initNs=prefixes):
    #     # print("\t" + r["r"])
    #     print("\t" + r["r"] + "\t\t" + str(r["label"]))

    dcat_graph = Graph()
    for s in chain(
            g.subjects(RDF.type, OWL.Ontology),
            g.subjects(RDF.type, SKOS.ConceptScheme),
            g.subjects(RDF.type, DCAT.Dataset),
            g.subjects(RDF.type, DCATS.Dataset),
            g.subjects(RDF.type, PROF.Profile),
            g.subjects(RDF.type, LOCI.Linkset),
            g.subjects(RDF.type, LOCIS.Linkset),
            g.subjects(RDF.type, REG.Register),
            g.subjects(RDF.type, IRG.IRIRegister),
    ):
        dcat_graph.add((s, RDF.type, DCAT.Resource))
        # title
        for o in chain(
                g.objects(subject=s, predicate=SKOS.prefLabel),
                g.objects(subject=s, predicate=DC.title),
                g.objects(subject=s, predicate=DCTERMS.title),
                g.objects(subject=s, predicate=RDFS.label),
        ):
            dcat_graph.add((s, DCTERMS.title, o))

        # description
        for o in chain(
                g.objects(subject=s, predicate=SKOS.definition),
                g.objects(subject=s, predicate=DC.description),
                g.objects(subject=s, predicate=DCTERMS.description),
                g.objects(subject=s, predicate=RDFS.comment),
        ):
            dcat_graph.add((s, DCTERMS.description, o))

        # created
        for o in chain(
                g.objects(subject=s, predicate=DCTERMS.created),
                g.objects(subject=s, predicate=DCTERMS.issued),
                g.objects(subject=s, predicate=DCTERMS.date),
        ):
            dcat_graph.add((s, DCTERMS.created, o))

        # modified
        for o in g.objects(subject=s, predicate=DCTERMS.modified):
            dcat_graph.add((s, DCTERMS.modified, o))

        # creator
        for o in g.objects(subject=s, predicate=DCTERMS.creator):
            dcat_graph.add((s, DCTERMS.creator, o))

        # publisher
        for o in g.objects(subject=s, predicate=DCTERMS.publisher):
            dcat_graph.add((s, DCTERMS.publisher, o))

        # identifier
        dcat_graph.add((
            s,
            DCTERMS.identifier,
            Literal(
                str(s)
                    .replace("https://linked.data.gov.au/", "")
                    .replace("http://linked.data.gov.au/", "")
                    .replace("/", "-"), datatype=XSD.token
            )))

        # codeRepo
        for o in g.objects(subject=s, predicate=SDO.codeRepository):
            dcat_graph.add((s, SDO.codeRepository, Literal(str(o), datatype=XSD.anyURI)))

        # break

    return dcat_graph


if __name__ == "__main__":
    iris = [
        "https://linked.data.gov.au/dataset",
        "https://linked.data.gov.au/dataset/addr1605mb11",
        "https://linked.data.gov.au/dataset/addr1605mb16",
        "https://linked.data.gov.au/dataset/addrcatch",
        "https://linked.data.gov.au/dataset/addrmb11",
        "https://linked.data.gov.au/dataset/addrmb16",
        "https://linked.data.gov.au/dataset/agiftcrsth",
        "https://linked.data.gov.au/dataset/asgs2011",
        "https://linked.data.gov.au/dataset/asgs2016",
        "https://linked.data.gov.au/dataset/energy",
        "https://linked.data.gov.au/dataset/geofabric",
        "https://linked.data.gov.au/dataset/gnaf",
        "https://linked.data.gov.au/dataset/gnaf-2016-05",
        "https://linked.data.gov.au/dataset/mb16cc",
        "https://linked.data.gov.au/dataset/mb16mb11",
        "https://linked.data.gov.au/dataset/placenames",
        "https://linked.data.gov.au/dataset/qldgeofeatures",
        "https://linked.data.gov.au/def",
        "https://linked.data.gov.au/def/address-type",
        "https://linked.data.gov.au/def/agop",
        "https://linked.data.gov.au/def/agrif",
        "https://linked.data.gov.au/def/asgs",
        "https://linked.data.gov.au/def/auspix",
        "https://linked.data.gov.au/def/australian-phone-area-codes",
        "https://linked.data.gov.au/def/australian-states-and-territories",
        "https://linked.data.gov.au/def/borehole-design",
        "https://linked.data.gov.au/def/borehole-drilling-method",
        "https://linked.data.gov.au/def/borehole-purpose",
        "https://linked.data.gov.au/def/borehole-start-point",
        "https://linked.data.gov.au/def/borehole-status-event",
        "https://linked.data.gov.au/def/borehole-sub-purpose",
        "https://linked.data.gov.au/def/crs",
        "https://linked.data.gov.au/def/data-access-rights",
        "https://linked.data.gov.au/def/dataciteroles",
        "https://linked.data.gov.au/def/dataset",
        "https://linked.data.gov.au/def/datatype",
        "https://linked.data.gov.au/def/depth-reference",
        "https://linked.data.gov.au/def/earth-science-data-category",
        "https://linked.data.gov.au/def/fsdf",
        "https://linked.data.gov.au/def/ga-vocpub",
        "https://linked.data.gov.au/def/gba",
        "https://linked.data.gov.au/def/geo-commodities",
        "https://linked.data.gov.au/def/geoadminfeatures",
        "https://linked.data.gov.au/def/geofabric",
        "https://linked.data.gov.au/def/geofeatures",
        "https://linked.data.gov.au/def/geological-observation-instrument",
        "https://linked.data.gov.au/def/geological-observation-method",
        "https://linked.data.gov.au/def/geological-observation-type",
        "https://linked.data.gov.au/def/geological-sites",
        "https://linked.data.gov.au/def/geometry-roles",
        "https://linked.data.gov.au/def/geoqk",
        "https://linked.data.gov.au/def/georesource-report",
        "https://linked.data.gov.au/def/geou",
        "https://linked.data.gov.au/def/geox",
        "https://linked.data.gov.au/def/gnaf",
        "https://linked.data.gov.au/def/gsq-alias",
        "https://linked.data.gov.au/def/gsq-dataset-theme",
        "https://linked.data.gov.au/def/gsq-roles",
        "https://linked.data.gov.au/def/gsq-sample-facility",
        "https://linked.data.gov.au/def/iso11179-6/RolesAndResponsibilities",
        "https://linked.data.gov.au/def/iso19115-1/RoleCode",
        "https://linked.data.gov.au/def/iso19160-1-address",
        "https://linked.data.gov.au/def/iso19160-1-address-nz-profile",
        "https://linked.data.gov.au/def/loci",
        "https://linked.data.gov.au/def/minerals",
        "https://linked.data.gov.au/def/observation-detail-type",
        "https://linked.data.gov.au/def/organisation-activity-status",
        "https://linked.data.gov.au/def/organisation-name-types",
        "https://linked.data.gov.au/def/organisation-type",
        "https://linked.data.gov.au/def/party-identifier-type",
        "https://linked.data.gov.au/def/party-relationship",
        "https://linked.data.gov.au/def/phs",
        "https://linked.data.gov.au/def/placenames",
        "https://linked.data.gov.au/def/plot",
        "https://linked.data.gov.au/def/project",
        "https://linked.data.gov.au/def/qld-resource-permit",
        "https://linked.data.gov.au/def/qld-resource-permit-status",
        "https://linked.data.gov.au/def/qld-utm-zones",
        "https://linked.data.gov.au/def/queensland-crs",
        "https://linked.data.gov.au/def/reg-status",
        "https://linked.data.gov.au/def/report-detail-type",
        "https://linked.data.gov.au/def/report-status",
        "https://linked.data.gov.au/def/resource-project-lifecycle",
        "https://linked.data.gov.au/def/result-type",
        "https://linked.data.gov.au/def/sample-detail-type",
        "https://linked.data.gov.au/def/sample-location-status",
        "https://linked.data.gov.au/def/sample-location-types",
        "https://linked.data.gov.au/def/sample-material",
        "https://linked.data.gov.au/def/sample-preparation-methods",
        "https://linked.data.gov.au/def/sample-relationship",
        "https://linked.data.gov.au/def/sample-type",
        "https://linked.data.gov.au/def/seismic-dimensionality",
        "https://linked.data.gov.au/def/seismic-sampling-method",
        "https://linked.data.gov.au/def/site-detail-type",
        "https://linked.data.gov.au/def/site-relationships",
        "https://linked.data.gov.au/def/site-status",
        "https://linked.data.gov.au/def/su",
        "https://linked.data.gov.au/def/survey-detail-type",
        "https://linked.data.gov.au/def/survey-method",
        "https://linked.data.gov.au/def/survey-relationship-type",
        "https://linked.data.gov.au/def/survey-status",
        "https://linked.data.gov.au/def/survey-type",
        "https://linked.data.gov.au/def/telephone-type",
        "https://linked.data.gov.au/def/trs",
        "https://linked.data.gov.au/org",
        "https://linked.data.gov.au/reg/",
    ]

    # download_rdf(iris)
    check_rdf("catalogue")
