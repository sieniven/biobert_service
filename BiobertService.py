import os
import json
import logging

from rq import Queue
from redis import Redis

from Biobert import Biobert
from BiobertModel import BiobertModel
from GTT.Service import Service

class BiobertService(Service):
    def __init__(self, RedisHost='localhost'):
        Service.__init__(self)
        self.logger = logging.getLogger("GTT.Biobert.Service")
        self.jobs = []
        self.q = Queue(connection=Redis(RedisHost))

        self.biobert = Biobert()
        self.title_predictions = []
        self.abstract_predictions = []

    def on_post(self, req, resp):
        data = json.loads(req.stream.read(req.content_length or 0))
        self.logger.debug(f"Attempting to post use handlers {str(self.posthandlers)}")
        
        self.jobs.append(self.q.enqueue(self.processDoc,
                                        on_success = self.report_success,
                                        on_failure = self.report_failure,
                                        kwargs={"data": data,
                                                "handlers": self.posthandlers}))

    def processDoc(self, data, handlers=[]):
        input = BiobertModel(data)
        self.biobert.load_data(input)

        # run prediction for input data
        self.biobert.predict()

        # process data
        input.get_biobert_output(self.biobert.index, self.biobert.ntokens_title[-1], 
            self.biobert.ntokens_abstract[-1], self.biobert.output_title[-1], self.biobert.output_abstract[-1])
        input.recognize()
        self.write_predictions(input)

        id = input.id
        n = len(input.entities)
        self.logger.info(f"NER finished for {id} with {n} entities recognized with Biobert")       
        input.post_one(handlers)
        
        return input

    def report_success(self, job, connection, result, *args, **kwargs):
        pass

    def report_failure(self, job, connection, type, value, traceback):
        self.logger.error(traceback)

    def write_predictions(self, input):
        modes = ["title", "abstract"]
        for mode in modes:
            path = os.path.join(self.biobert.output_dir, "predict_"+mode+".txt")
            with open(path, 'a', encoding="utf-8") as wf:
                line = str(self.biobert.index) + ": "

                if mode == "title":
                    for prediction in input.title_entities:
                        line += prediction + " "
                else:
                    for prediction in input.abstract_entities:
                        line += prediction + " "
                
                wf.write(line+'\n')
                wf.close()
                
    def process_ingest_dataset(self):
        models = []
        with open('../gtt_docker/ingest/ingestDataset.json') as f:
            input_data_list = json.loads("[" + f.read().replace("}{", "},{") +  "]")
        
        for data in input_data_list:
            model = BiobertModel(data)
            models.append(model)

        for input in models:
            self.biobert.load_data(input)

            # run prediction for input data
            self.biobert.predict()
            input.get_biobert_output(self.biobert.index, self.biobert.ntokens_title[-1], 
                self.biobert.ntokens_abstract[-1], self.biobert.output_title[-1], self.biobert.output_abstract[-1])
            input.recognize()

            # log predictions
            self.write_predictions(input)