from typing import Union, List
import httpx
import asyncio
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DCAT, DCTERMS, DC, PROF, XSD, SDO
from itertools import chain
import re
import pyshacl
import json
import shutil


REG = Namespace("http://purl.org/linked-data/registry#")
IRG = Namespace("https://linked.data.gov.au/def/irg#")
LOCI = Namespace("http://linked.data.gov.au/def/loci#")

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
    "loci": "https://linked.data.gov.au/def/loci#",
    "sdo": SDO
}

PROFILES_RECOGNISED = [
    "https://www.w3.org/TR/vocab-dcat/",            # DCAT
    "https://www.w3.org/TR/skos-reference/",        # SKOS
    "https://schema.org",                           # schema.org
    "https://www.w3.org/TR/dx-prof/",               # PROF
    "https://w3id.org/profile/vocpub",              # VocPub
    "https://linked.data.gov.au/def/ga-vocpub",     # GA's Profile of VocPub
    "https://linked.data.gov.au/def/agop",          # Aust Gov Ont Profile
]

TEMP_DATA_DIR = Path(__file__).parent.parent / "temp"
DATA_DIR = Path(__file__).parent.parent / "data"
VALIDATORS_DIR = Path(__file__).parent.parent / "tools" / "validators"


def file_to_iri(f: Path) -> URIRef:
    return URIRef("https://linked.data.gov.au/" + str(f.name).replace(".ttl", "").replace("--", "/"))


def iri_to_file(iri: URIRef) -> Path:
    return Path(TEMP_DATA_DIR / Path(str(iri).replace("https://linked.data.gov.au/", "").replace("/", "--") + ".ttl"))


def iri_to_token(iri: URIRef) -> str:
    f = iri_to_file(iri)
    return str(f).replace(str(TEMP_DATA_DIR) + "/", "").replace(".ttl", "").replace("--", "-")


async def httpx_get_many(urls, headers=None):
    """Run httpx.get for all given urls, asynchronously
    """
    async def get_async(url):
        try:
            async with httpx.AsyncClient() as client:
                return await client.get(url, headers=headers)
        except Exception as e:
            print("Exception for {}".format(url))
            print(e)
            return httpx.Response(status_code=500)

    resps = await asyncio.gather(*map(get_async, urls))
    return tuple(zip(urls, resps))


def get_repo_url(url: str) -> Union[str, None]:
    """Given a URL, this method return a repo URL if it can determine one else None"""
    # get repos
    repos = ["github", "bitbucket", "gitlab", "githack", "githubusercontent"]
    # https://bitbucket.org/surroundbitbucket/sop-recipe-govkg/src/master/edg/linksets/cofogcofoga.ttl
    # https://github.com/AGLDWG/agrif-ont/blob/master/agrif.ttl
    # https://raw.githubusercontent.com/CSIRO-enviro-informatics/longspine-ont/master/longspine.ttl
    # https://raw.githack.com/CSIRO-enviro-informatics/loci-ont/master/loci.ttl
    # https://gitlab.ogc.org/ogc/t16-d017-dggs-and-dggs-api-er/-/blob/master/ER/er.adoc
    if any(repo in str(url) for repo in repos):
        # 1. convert other GitHub forms to plain GitHub
        repo_uri = str(url)
        repo_uri = repo_uri.replace("raw.githubusercontent.com", "github.com")
        repo_uri = repo_uri.replace("raw.githack.com", "github.com")

        # 2. extract segments
        pattern = "https:\/\/(gitlab[\.\w]+|bitbucket.org|github.com)\/([^\/]+)\/([^\/]+)\/"
        m = re.match(pattern, repo_uri)
        repo_uri = Literal("https://{}/{}/{}/".format(m.group(1), m.group(2), m.group(3)), datatype=XSD.anyURI)
        return repo_uri
    else:
        return None


def download_default_profile_rdf(urls: List[str]):
    """Downloads default profile RDF for given URLs iff HTTPS status is 200 with Accept header of text/turtle.

    Also records the repositories used to serve any URI's RDF as a <uri> sdo:codeRepository "repo-url"^^xsd:anyURI.

    Replaces all http://linked.data.gov.au with  https://linked.data.gov.au"""
    if Path.is_dir(TEMP_DATA_DIR):
        print("Clearing Resources cache")
        shutil.rmtree(TEMP_DATA_DIR)
    else:
        print("Creating Resources cache")
    TEMP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading default RDF for each resource...")

    results = asyncio.run(httpx_get_many(urls, headers={"Accept": "text/turtle"}))
    repos = Graph()
    repos.bind("sdo", SDO)

    # for all URLs that return an RDF result...
    for result in [(r[0], r[1].text, r[1].url) for r in results if r[1].status_code == 200]:
        # replace all mentions of http://linked.data.gov.au with  https://linked.data.gov.au
        data = result[1].replace("http://linked.data.gov.au", "https://linked.data.gov.au")
        data = data.replace("https://www.w3.org/ns/dcat#", "http://www.w3.org/ns/dcat#")

        # simple Turtle validation
        if any(x in result[1] for x in ["@prefix", "PREFIX"]):
            # store the RDF in a file
            open(str(iri_to_file(URIRef(result[0]))), "w").write(data)

        # add repo triples, whenever we extract them
        repo_url = get_repo_url(result[2])
        if repo_url is not None:
            repos.add((URIRef(str(result[0])), SDO.codeRepository, Literal(repo_url, datatype=XSD.anyURL)))

    # store repo triples
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    repos.serialize(destination=str(DATA_DIR / "repos.ttl"), format="ttl")

    print("...complete")


def download_alt_profile_rdf(urls: List[str]):
    print("Downloading alternate profiles RDF for each resource...")
    urls = [url + "?_profile=alt" for url in urls]
    results = asyncio.run(httpx_get_many(urls, headers={"Accept": "text/turtle", "Accept-Profile": "<http://www.w3.org/ns/dx/connegp/altr>"}))
    TEMP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for result in [(r[0], r[1].text, r[1].url) for r in results if r[1].status_code == 200]:
        # replace all mentions of http://linked.data.gov.au with  https://linked.data.gov.au
        data = result[1].replace("http://linked.data.gov.au", "https://linked.data.gov.au")
        data = data.replace("https://www.w3.org/ns/dcat#", "http://www.w3.org/ns/dcat#")

        # simple Turtle validation
        if result[1].startswith("@"):
            # store the RDF in a file
            graph_file_name = result[0]\
                                  .replace("?_profile=alt", "")\
                                  .replace("https://linked.data.gov.au/", "")\
                                  .replace("/", "--") + "-alt.ttl"
            open(str(TEMP_DATA_DIR / graph_file_name), "w").write(data)

    print("...complete")


def make_catalogue_items():
    """Reads RDF files from a given directory and generates a CatPrez-compatible data file from them - items.trig"""
    cat = Graph()
    for f in TEMP_DATA_DIR.iterdir():
        if f.name.endswith(".ttl"):
            try:
                print("reading " + str(f.name))
                g = Graph().parse(str(f), format="ttl")

                # add original graph to catalogue
                cat += g
                # add DCAT info to catalogue
                cat += build_dcat_profile(g)
            except Exception as e:
                print("{} un-parsable Turtle".format(f))

                # pathlib.Path.unlink(f)

    # merge in repos.ttl
    cat.parse(str(DATA_DIR / "repos.ttl"), format="ttl")

    print("serializing")
    for k, v in PREFIXES.items():
        cat.bind(k, v)
    cat.serialize(destination=str(DATA_DIR / "items.ttl"), format="ttl")


def build_dcat_profile(g: Graph, target_uri: URIRef):
    dcat_graph = Graph()
    for o in g.objects(subject=target_uri, predicate=RDF.type):
        if o in [
            OWL.Ontology,
            SKOS.ConceptScheme,
            DCAT.Catalog,
            DCAT.Dataset,
            PROF.Profile,
            LOCI.Linkset,
            REG.Register,
            IRG.IRIRegister
        ]:
            print("adding {}".format(o))
            dcat_graph.add((target_uri, RDF.type, DCAT.Resource))
            dcat_graph.add((target_uri, DCTERMS.type, o))

        # title
        for o in chain(
            g.objects(subject=target_uri, predicate=SKOS.prefLabel),
            g.objects(subject=target_uri, predicate=DC.title),
            g.objects(subject=target_uri, predicate=DCTERMS.title),
            g.objects(subject=target_uri, predicate=RDFS.label),
        ):
            dcat_graph.add((target_uri, DCTERMS.title, o))

        # description
        for o in chain(
            g.objects(subject=target_uri, predicate=SKOS.definition),
            g.objects(subject=target_uri, predicate=DC.description),
            g.objects(subject=target_uri, predicate=DCTERMS.description),
            g.objects(subject=target_uri, predicate=RDFS.comment),
        ):
            dcat_graph.add((target_uri, DCTERMS.description, o))

        # created
        for o in chain(
            g.objects(subject=target_uri, predicate=DCTERMS.created),
            g.objects(subject=target_uri, predicate=DCTERMS.issued),
            g.objects(subject=target_uri, predicate=DCTERMS.date),
        ):
            dcat_graph.add((target_uri, DCTERMS.created, o))

        # modified
        # for o in g.objects(subject=target_uri, predicate=DCTERMS.modified):
        #     dcat_graph.add((s, DCTERMS.modified, o))

        # creator
        # for o in g.objects(subject=target_uri, predicate=DCTERMS.creator):
        #     dcat_graph.add((s, DCTERMS.creator, o))

        # publisher
        # for o in g.objects(subject=target_uri, predicate=DCTERMS.publisher):
        #     dcat_graph.add((s, DCTERMS.publisher, o))

        # identifier
        dcat_graph.add((
            target_uri,
            DCTERMS.identifier,
            Literal(iri_to_token(target_uri), datatype=XSD.token)
        ))

        # codeRepo
        for o in g.objects(subject=target_uri, predicate=SDO.codeRepository):
            dcat_graph.add((target_uri, SDO.codeRepository, Literal(str(o), datatype=XSD.anyURI)))

    return dcat_graph


def build_dcat_profile_all():
    for f in TEMP_DATA_DIR.iterdir():
        if f.name.endswith(".ttl"):
            try:
                print("enhancing {}...".format(str(f.name)))
                g = Graph().parse(str(f), format="ttl")
                for k, v in PREFIXES.items():
                    g.bind(k, v)

                g += build_dcat_profile(g, file_to_iri(f))

                g.serialize(str(TEMP_DATA_DIR / f.name), format="ttl")
            except Exception as e:
                print("...could not build")
                print("ERROR: {}".format(e))


def calculate_conforms_to():
    for f in TEMP_DATA_DIR.iterdir():
        # load the graph of the Resource, determine what type the main object's class is
        main_obj_uri = file_to_iri(f)
        g = Graph().parse(str(f), format="ttl")
        print(main_obj_uri)
        for o in g.objects(subject=main_obj_uri, predicate=DCTERMS.type):
            print(" type: {}".format(o))

        # v = pyshacl.validate(str(f), shacl_graph=str(Path(VALIDATORS_DIR / "agop.ttl")))
        # if v[0]:
        #     print(f.name)


if __name__ == "__main__":
    # 1. get the list of IRIs to attempt to catalogue
    # TODO: replace this static list with a dynamic one from the IRI Registry
    iris = [
        "https://linked.data.gov.au/dataset",
        "https://linked.data.gov.au/dataset/addr1605mb11",
        "https://linked.data.gov.au/dataset/addr1605mb16",
        "https://linked.data.gov.au/dataset/addrcatch",
        "https://linked.data.gov.au/dataset/addrmb11",
        "https://linked.data.gov.au/dataset/addrmb16",
        "https://linked.data.gov.au/dataset/agiftcrsth",
        # "https://linked.data.gov.au/dataset/asgs2011", -- returns asgs2016 IRI
        "https://linked.data.gov.au/dataset/asgs2016",
        "https://linked.data.gov.au/dataset/energy",
        "https://linked.data.gov.au/dataset/geofabric",
        "https://linked.data.gov.au/dataset/gnaf",
        # "https://linked.data.gov.au/dataset/gnaf-2016-05", -- return gnaf IRI
        "https://linked.data.gov.au/dataset/mb16cc",
        # "https://linked.data.gov.au/dataset/mb16mb11", -- waiting for PR to match Resource IRI to PID IRI
        "https://linked.data.gov.au/dataset/placenames",
        "https://linked.data.gov.au/dataset/qldgeofeatures",
        "https://linked.data.gov.au/def",
        "https://linked.data.gov.au/def/address-type",
        "https://linked.data.gov.au/def/agop",
        "https://linked.data.gov.au/def/agrif",
        "https://linked.data.gov.au/def/asgs",
        # "https://linked.data.gov.au/def/auspix", -- prefix schema: undeclared
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
        # "https://linked.data.gov.au/def/gba", -- doesn't know it's owl PID IRI
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

    # 2. get default Profile RDF from each IRI
    #   - store in a Dataset, Graph per Resource
    download_default_profile_rdf(iris)

    # # X. get Alt Profiles RDF for each IRI, if we can see it
    # download_alt_profile_rdf(iris)
    # # X. for each Alt Profile result, get the RDF for each Profile we recognise
    # #   - add to each Resource's graph

    # 3. Build basic DCAT metadata for each Item
    build_dcat_profile_all()

    # 4. Calculate conformsTo for each Resource
    calculate_conforms_to()

    # 5. Store all result, with built-out DCAT properties, in a data file (data/catalogue.ttl)
#    make_catalogue_items(pathlib.Path(__file__).parent.parent / "catalogue")

    # # 5. for each Resource, generate seen conformsTo
    # #   - store results in separate graph
    #
    # # 5.
    # get_items_rdf("../catalogue")
    # get_catalogue_rdf()

