# -*- coding: utf-8 -*-


import io
import pandas as pd

from ast import literal_eval
from flask.views import MethodView
from flask import current_app, send_file
from flask import (Blueprint, jsonify, flash, redirect,
                   request, url_for)
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.auth.helper import token_required
from app.import_export.helper import (allowed_file, parse_cfg,
                                      get_category_model)
from app.nagios_functions.helper import restartNagios
from app.nagios_functions.helper import overwriteAllNagiosConfigFiles


import_export = Blueprint('import_export', __name__)


class CFGView(MethodView):

    def post(self, jwt):

        if not 'file' in request.files:
            return jsonify(error=True, msg="Request contains no files.")

        file = request.files['file']
        if file.filename == '':
            return jsonify(error=True, msg="No selected file")

        failed_entries = dict()

        if file and allowed_file(file.filename, ['cfg']):

            data = parse_cfg(file.read().decode("utf-8"))

            if not data:
                return jsonify(error=True,
                               msg='Failed to parse: {}'.format(file.filename))

            for category in data:

                category_model = get_category_model(category)

                eval_cols = category_model.eval_columns()

                if not category_model:
                    return jsonify(error=True,
                                   msg='Unsupported category: {}.'.format(
                                       category))

                cols_default_mapping = category_model.cols_default_mapping()
                if category == 'host':
                    for index, each in enumerate(cols_default_mapping):

                        if each[0] == 'active_checks_enabled':
                            cols_default_mapping[index][1] = True
                        elif each[0] == 'passive_checks_enabled':
                            cols_default_mapping[index][1] = True
                        elif each[0] == 'check_period':
                            cols_default_mapping[index][1] = "24x7"

                all_rows = data[category]
                failed_rows = []
                model_objects = []

                for row in all_rows:
                    init_args = []
                    for col_name, default_val in category_model.cols_default_mapping():
                        val = row.get(col_name)
                        if val:
                            if col_name in eval_cols:
                                val = literal_eval(val.strip()) if val else default_val
                        else:
                            val = default_val
                        init_args.append(val)

                    model_objects.append(category_model(*init_args))

                for model_obj in model_objects:
                    try:
                        model_obj.insert_or_update()
                    except IntegrityError as ie:
                        print(ie)
                        # Todo log warn
                        category_model.rollback()
                        failed_rows.append({'reason': 'IntegrityError',
                                            'data': model_obj.serialize()})
                    except Exception as e:
                        print(e)
                        # Todo log warn
                        category_model.rollback()
                        failed_rows.append({'reason': 'Unknown',
                                            'data': model_obj.serialize()})
                if failed_rows:
                    failed_entries[category] = failed_rows

            overwriteAllNagiosConfigFiles()
            restartNagios()
            if failed_entries:
                return jsonify(error=True, msg='Not all config data got insert.',
                               failed_rows=failed_entries)

            return jsonify(error=False, msg='successful')

        return jsonify(error=False, msg='File format no supported.')


class CSVView(MethodView):

    def post(self, jwt, category):
        if not 'file' in request.files:
            return jsonify(error=True, msg="Request contains no files.")

        file = request.files['file']
        if file.filename == '':
            return jsonify(error=True, msg="No selected file")

        if file and allowed_file(file.filename, ['csv']):

            df = pd.read_csv(file)
            df = df.where((pd.notnull(df)), None)

            category_model = get_category_model(category)
            if not category_model:
                return jsonify(error=True,
                               msg='Unsupported category: {}.'.format(category))

            if category == 'hosts':
                df['active_checks_enabled'] = True
                df['passive_checks_enabled'] = True
                df['check_period'] = "24x7"

            all_rows = df.to_dict(orient='records')

            failed_rows = []
            model_objects = []

            for row in all_rows:
                init_args = [row.get(col_name, default_val) for col_name,
                                    default_val in category_model.cols_default_mapping()]
                model_objects.append(category_model(*init_args))


            for model_obj in model_objects:
                try:
                    model_obj.insert_or_update()
                except IntegrityError as ie:
                    print(ie)
                    #Todo log warn
                    category_model.rollback()
                    failed_rows.append({'reason': 'IntegrityError',
                                        'data': model_obj.serialize()})
                except Exception as e:
                    print(e)
                    # Todo log warn
                    category_model.rollback()
                    failed_rows.append({'reason': 'Unknown',
                                        'data': model_obj.serialize()})

            overwriteAllNagiosConfigFiles()
            restartNagios()
            if failed_rows:
                return jsonify(error=True, msg='Not all rows got insert.',
                               failed_rows=failed_rows)

            return jsonify(error=False, msg='successful')

        return jsonify(error=False, msg='File format no supported.')

    def get(self, jwt, category):
        """
        :param jwt:
        :param category:
        :return:
        """
        try:
            drop_cols = ['id', 'added_time', 'modified_time']
            category_model = get_category_model(category)
            if not category_model:
                return jsonify(error=True,
                               msg='Unsupported category: {}.'.format(category))

            model_objects = category_model.get_all()
            if not model_objects:
                return jsonify(error=False, msg='No data found.')

            serialized_data = [each.serialize() for each in model_objects]

            buffer = io.StringIO()
            df = pd.DataFrame(serialized_data)

            for col in drop_cols:
                del df[col]

            df.to_csv(buffer, index=False, encoding='utf-8')

            mem = io.BytesIO()
            mem.write(buffer.getvalue().encode('utf-8'))
            mem.seek(0)
            buffer.close()

            return send_file(mem, attachment_filename='{}.csv'.format(category),
                             mimetype='text/csv', as_attachment=True)
        except Exception:
            return jsonify(error=True, msg='Failed to generate reports.')


cfg_view = token_required(CFGView.as_view('cfg_view'))
csv_view = token_required(CSVView.as_view('csv_view'))


import_export.add_url_rule(
    '/cfg',
    view_func=cfg_view,
    methods=['GET', 'POST']
)

import_export.add_url_rule(
    '/csv/<string:category>',
    view_func=csv_view,
    methods=['GET', 'POST']
)
