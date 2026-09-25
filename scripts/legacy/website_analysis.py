import pandas as pd
import plotly.graph_objects as go
import datetime
import os


# --- 1. HELPER FUNCTIONS ---

def minus_years(dt, years):
    try:
        return dt.replace(year=dt.year - years)
    except ValueError:
        return dt + (datetime.date(dt.year - years, 1, 1) - datetime.date(dt.year, 1, 1))


# --- 2. CHART MODULES ---

def get_last_year_chart(dataframe, active_users, base_path, max_total):
    now = datetime.datetime.now()
    one_year = minus_years(now, 1)
    df = dataframe[dataframe['date'] >= one_year].copy()
    df["date"] = df["date"].astype("datetime64[M]")
    movie_totals = df.groupby(['user', 'movie', 'date'])['Score'].sum().reset_index()
    monthly_avg = movie_totals.groupby(['user', 'date'])['Score'].mean().reset_index()
    group_mean = monthly_avg.groupby('date')['Score'].mean().reset_index()
    group_mean['user'] = 'Mean'
    final_df = pd.concat([group_mean, monthly_avg], axis=0)
    user_list = ['Mean'] + [u for u in active_users if u in monthly_avg['user'].unique()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=group_mean['date'], y=group_mean['Score'], mode='lines+markers',
                             line=dict(width=4, color='#636EFA'), name='Mean'))
    buttons = []
    for user in user_list:
        u_df = final_df[final_df['user'] == user].sort_values('date')
        buttons.append(dict(method='update', label=user, args=[{'y': [u_df['Score']], 'x': [u_df['date']]}]))
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.15)],
                      yaxis=dict(range=[-0.5, max_total + 0.5], title="Average Score"), paper_bgcolor='#dfe0f7',
                      plot_bgcolor='#bec1ef', showlegend=False)
    out_path = os.path.join(base_path, "analysis1/year-votes-chart.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


def get_top_ten_movie_chart(dataframe, active_users, base_path, max_total, mode='top'):
    movie_totals = dataframe.groupby(['user', 'movie'])['Score'].sum().reset_index()
    avg_totals = movie_totals.groupby('movie')['Score'].mean().reset_index()
    avg_totals['user'] = 'Mean'
    combined = pd.concat([avg_totals, movie_totals], axis=0)
    entities = ['Mean'] + active_users
    master_df = pd.DataFrame()
    ascending = (mode == 'bottom')
    for e in entities:
        e_df = combined[combined['user'] == e].sort_values(by='Score', ascending=ascending).head(10)
        master_df = pd.concat([master_df, e_df], axis=0)
    initial = master_df[master_df['user'] == 'Mean']
    fig = go.Figure(go.Bar(x=initial['movie'], y=initial['Score'], marker_color='#636EFA'))
    buttons = []
    for e in entities:
        m_df = master_df[master_df['user'] == e]
        if not m_df.empty:
            buttons.append(dict(method='update', label=e, args=[{'y': [m_df['Score']], 'x': [m_df['movie']]}]))
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.15)],
                      yaxis=dict(range=[0, max_total], title="Total Score"), paper_bgcolor='#dfe0f7',
                      plot_bgcolor='#bec1ef')
    fname = "top-10.html" if mode == 'top' else "bottom-10.html"
    out_path = os.path.join(base_path, f"analysis1/{fname}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


def get_average_score_per_voter(dataframe, active_users, base_path, max_total, metric_max_map):
    movie_totals = dataframe.groupby(['user', 'movie'])['Score'].sum().reset_index()
    total_avg = movie_totals.groupby('user')['Score'].mean().reset_index()
    total_avg['Metric'] = 'Mean'
    metric_avg = dataframe.groupby(['user', 'Metric'])['Score'].mean().reset_index()
    final_df = pd.concat([total_avg, metric_avg], axis=0)
    final_df['Metric'] = final_df['Metric'].str.capitalize()
    initial = total_avg.sort_values(by='Score', ascending=False)
    fig = go.Figure(go.Bar(x=initial['user'], y=initial['Score'], marker_color='#636EFA'))
    metrics = ['Mean'] + sorted([m for m in final_df['Metric'].unique() if m != 'Mean'])
    buttons = []
    for m in metrics:
        m_df = final_df[final_df['Metric'] == m].sort_values(by='Score', ascending=False)
        current_max = max_total if m == 'Mean' else metric_max_map.get(m, 1.0)
        buttons.append(dict(method='update', label=m, args=[{'y': [m_df['Score']], 'x': [m_df['user']]}, {
            'yaxis': {'range': [0, current_max], 'title': f'Avg {m} Score'}}]))
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.15)], paper_bgcolor='#dfe0f7', plot_bgcolor='#bec1ef')
    out_path = os.path.join(base_path, "analysis2/voter-score.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


def get_difference_from_median_raters(dataframe, base_path):
    median_metrics = dataframe.groupby(['Metric', 'movie'])['Score'].median().reset_index()
    median_metrics.rename(columns={'Score': 'median_metric'}, inplace=True)
    df_delta = dataframe.merge(median_metrics, on=['Metric', 'movie'])
    df_delta['delta'] = df_delta['Score'] - df_delta['median_metric']
    metric_delta_df = df_delta.groupby(['user', 'Metric'])['delta'].mean().reset_index()
    movie_total_deltas = df_delta.groupby(['user', 'movie'])['delta'].sum().reset_index()
    mean_delta_df = movie_total_deltas.groupby(['user'])['delta'].mean().reset_index()
    mean_delta_df['Metric'] = 'Mean'
    final_df = pd.concat([mean_delta_df, metric_delta_df], axis=0)
    final_df['Metric'] = final_df['Metric'].str.capitalize()
    initial_data = mean_delta_df.sort_values(by='delta', ascending=False)
    fig = go.Figure(go.Bar(x=initial_data['user'], y=initial_data['delta'], marker_color='#636EFA'))
    buttons = []
    metric_list = ['Mean'] + sorted([m for m in final_df['Metric'].unique() if m != 'Mean'])
    for m in metric_list:
        m_df = final_df[final_df['Metric'] == m].sort_values(by='delta', ascending=False)
        buttons.append(dict(method='update', label=m, args=[{'y': [m_df['delta']], 'x': [m_df['user']]}, {
            'yaxis': {'zeroline': True, 'zerolinecolor': 'black', 'title': f'Avg {m} Diff from Median'}}]))
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.15)], paper_bgcolor='#dfe0f7', plot_bgcolor='#bec1ef')
    out_path = os.path.join(base_path, "analysis2/median-diff.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


def get_average_score_per_list_user(dataframe, user_config_df, base_path, max_total, metric_max_map):
    user_config_df.columns = user_config_df.columns.str.strip()
    name_map = dict(zip(user_config_df['full_name'], user_config_df['user_code']))
    active_codes = user_config_df[user_config_df['include'] == 1]['user_code'].tolist()
    df = dataframe.copy()
    df['List User Initials'] = df['list_user'].map(name_map)
    f_df = df[df['List User Initials'].isin(active_codes)].dropna(subset=['List User Initials'])
    clean_metrics = f_df.groupby(['List User Initials', 'movie', 'Metric'])['Score'].mean().reset_index()
    metric_avg = clean_metrics.groupby(['List User Initials', 'Metric'])['Score'].mean().reset_index()
    movie_totals = clean_metrics.groupby(['List User Initials', 'movie'])['Score'].sum().reset_index()
    total_avg = movie_totals.groupby('List User Initials')['Score'].mean().reset_index()
    total_avg['Metric'] = 'Mean'
    final_df = pd.concat([total_avg, metric_avg], axis=0)
    final_df['Metric'] = final_df['Metric'].str.capitalize()
    initial = total_avg.sort_values('Score', ascending=False)
    fig = go.Figure(go.Bar(x=initial['List User Initials'], y=initial['Score'], marker_color='#636EFA'))
    metrics = ['Mean'] + sorted([m for m in final_df['Metric'].unique() if m != 'Mean'])
    buttons = []
    for m in metrics:
        m_df = final_df[final_df['Metric'] == m].sort_values('Score', ascending=False)
        current_max = max_total if m == 'Mean' else metric_max_map.get(m, 1.0)
        buttons.append(dict(method='update', label=m, args=[{'y': [m_df['Score']], 'x': [m_df['List User Initials']]}, {
            'yaxis': {'range': [0, current_max], 'title': f'Avg {m} Score'}}]))
    fig.update_layout(updatemenus=[dict(buttons=buttons, x=0, y=1.15)], paper_bgcolor='#dfe0f7', plot_bgcolor='#bec1ef')
    out_path = os.path.join(base_path, "analysis2/nominator-score.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


def get_number_of_movies_attended(dataframe, base_path):
    attendance = dataframe.groupby('user')['movie'].nunique().reset_index()
    attendance = attendance.sort_values('movie', ascending=False)
    fig = go.Figure(go.Bar(x=attendance['user'], y=attendance['movie'], marker_color='#636EFA'))
    fig.update_layout(yaxis_title="Total Movies Rated", paper_bgcolor='#dfe0f7', plot_bgcolor='#bec1ef')
    out_path = os.path.join(base_path, "analysis1/movies-attended.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


def get_score_over_time_per_voter(dataframe, active_users, base_path):
    now = datetime.datetime.now()
    one_year_df = dataframe[dataframe['date'] >= minus_years(now, 1)].copy()
    one_year_df["date"] = one_year_df["date"].astype("datetime64[M]")
    totals = one_year_df.groupby(['user', 'date'])['Score'].sum().reset_index()
    fig = go.Figure()
    for user in active_users:
        u_df = totals[totals['user'] == user].sort_values('date')
        if not u_df.empty:
            fig.add_trace(go.Bar(name=user, x=u_df['date'], y=u_df['Score']))
    fig.update_layout(barmode='stack', paper_bgcolor='#dfe0f7', plot_bgcolor='#bec1ef',
                      legend=dict(orientation='h', y=1.1))
    out_path = os.path.join(base_path, "analysis1/score-over-time.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.write_html(out_path, include_plotlyjs='cdn')


# --- 3. MOVIE PAGE GENERATOR (UPDATED FOR CATEGORIES IN COLUMNS) ---


def generate_movie_pages(dataframe, base_path, metric_max_map, max_total):
    df = dataframe.copy()
    df['Metric'] = df['Metric'].str.capitalize()
    metrics_order = ['Enjoyable', 'Plot', 'Acting', 'Camera', 'Themes', 'Music', 'Casting', 'Wildcard']

    # CSS with Large Desktop Font and Mobile Scaling
    style_header = """
    <style>
        body { margin: 0; padding: 0; background: transparent; font-family: 'Lato', sans-serif; overflow: hidden; }

        .table-container {
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }

        table { 
            table-layout: auto; 
            width: 100%; 
            min-width: 550px; /* Increased to support larger font */
            border-collapse: collapse; 
            margin: 0; 
            font-size: 14px; /* Large readable text for Desktop */
        }

        /* Adjusted sticky column for larger labels */
        th:first-child, td:first-child { 
            width: 70px; 
            min-width: 70px;
            text-align: left; 
            padding-left: 8px;
            position: sticky;
            left: 0;
            background-color: white; 
            z-index: 2;
            border-right: 2px solid #dfe0f7;
        }

        th:first-child {
            background-color: #151853; 
            color: white;
            z-index: 3;
        }

        th, td { 
            border: 1px solid #dfe0f7; 
            text-align: center; 
            padding: 4px 2px; /* Breathable spacing */
            white-space: nowrap;
        }

        th { 
            font-family: 'Poppins', sans-serif !important; 
            background-color: #151853; 
            color: white;
            line-height: 1.2;
        }

        .total-col { background-color: #bec1ef !important; font-weight: bold; }
        .max-row { background-color: #dfe0f7 !important; font-style: italic; }

        /* Media query to scale down for phones */
        @media screen and (max-width: 600px) {
            table { 
                font-size: 11.5px; 
                min-width: 480px;
            }
            th:first-child, td:first-child { 
                width: 55px; 
                min-width: 55px; 
                padding-left: 4px;
            }
        }
    </style>
    """

    def generate_html_table(df_to_export, table_type):
        html = '<div class="table-container"><table>'
        html += '<thead><tr><th></th>'
        for col in df_to_export.columns:
            html += f'<th>{col}</th>'
        html += '</tr></thead><tbody>'
        for idx, row in df_to_export.iterrows():
            row_attr = ' class="max-row"' if (table_type == 'summary' and idx == 'Max') else ""
            html += f'<tr{row_attr}>'
            html += f'<td>{idx}</td>'
            for col in df_to_export.columns:
                cell_class = ' class="total-col"' if col == 'Total' else ""

                # NEW FORMATTING LOGIC HERE
                val = row[col]
                formatted_val = f"{round(val, 2):g}"

                html += f'<td{cell_class}>{formatted_val}</td>'
            html += '</tr>'
        html += '</tbody></table></div>'
        return style_header + html

    movies_root = os.path.join(base_path, "movies")
    os.makedirs(movies_root, exist_ok=True)

    for movie in df['movie'].unique():
        safe_name = "".join([c for c in movie if c.isalnum() or c in (' ', '-', '_')]).strip()
        movie_path = os.path.join(movies_root, safe_name)
        os.makedirs(movie_path, exist_ok=True)

        m_df = df[df['movie'] == movie]
        pivot = m_df.pivot_table(index='user', columns='Metric', values='Score', aggfunc='mean')
        for m in metrics_order:
            if m not in pivot.columns: pivot[m] = 0.0
        pivot = pivot[metrics_order]
        pivot['Total'] = pivot.sum(axis=1)

        summary_data = []
        avg_row = pivot.mean();
        avg_row.name = 'Mean'
        summary_data.append(avg_row)
        max_vals = [metric_max_map.get(m, 0) for m in metrics_order] + [max_total]
        max_row = pd.Series(max_vals, index=pivot.columns, name='Max')
        summary_data.append(max_row)
        diff_row = max_row - avg_row;
        diff_row.name = 'Diff'
        summary_data.append(diff_row)
        summary_df = pd.DataFrame(summary_data)

        with open(os.path.join(movie_path, "user_breakdown.html"), "w") as f:
            f.write(generate_html_table(pivot, 'breakdown'))
        with open(os.path.join(movie_path, "summary.html"), "w") as f:
            f.write(generate_html_table(summary_df, 'summary'))


def generate_callout_visuals(dataframe, max_ratings_df, base_path):
    df = dataframe.copy()
    df['Metric'] = df['Metric'].str.capitalize()

    # 1. Map metric maximums
    m_max_map = {k.capitalize(): v for k, v in max_ratings_df.set_index('Metric')['max_score'].to_dict().items()}

    # 2. Global Ranks & Totals
    user_movie_totals = df.groupby(['movie', 'user'])['Score'].sum().reset_index()
    movie_avg_totals = user_movie_totals.groupby('movie')['Score'].mean().sort_values(ascending=False)
    movie_ranks = movie_avg_totals.rank(method='min', ascending=False)
    total_movies = len(movie_avg_totals)

    # 3. Category Averages
    movie_metric_avgs = df.groupby(['movie', 'Metric'])['Score'].mean().reset_index()

    # 4. Controversy (Standard Deviation)
    movie_sd = user_movie_totals.groupby('movie')['Score'].std().fillna(0)

    icons = {
        'Enjoyable': '😊', 'Plot': '📖', 'Acting': '🎭', 'Camera': '🎥',
        'Themes': '💡', 'Music': '🎵', 'Casting': '👥', 'Wildcard': '🃏'
    }

    style = """
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { margin: 0; padding: 0; background: transparent; font-family: 'Poppins', sans-serif; overflow: hidden; }
            .grid-container {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                grid-template-rows: repeat(2, min-content);
                gap: 6px;
                padding: 4px;
                box-sizing: border-box;
            }
            .callout-card {
                background: white;
                border-radius: 6px;
                padding: 4px 2px;
                text-align: center;
                box-shadow: 0 1px 4px rgba(0,0,0,0.05);
                border: 1px solid #dfe0f7;
                display: flex;
                flex-direction: column;
                justify-content: center;
                min-height: 50px;
            }
            .label { font-size: 7px; text-transform: uppercase; color: #7175c0; margin-bottom: 1px; font-weight: 600; }
            .value { font-size: 9.5px; font-weight: 700; color: #151853; line-height: 1.1; }
            .icon { font-size: 13px; margin-bottom: 1px; }
        </style>
    </head>
    """

    movies_root = os.path.join(base_path, "movies")
    for movie in df['movie'].unique():
        safe_name = "".join([c for c in movie if c.isalnum() or c in (' ', '-', '_')]).strip()
        movie_path = os.path.join(movies_root, safe_name)
        os.makedirs(movie_path, exist_ok=True)

        # --- Data Prep for specific movie ---
        m_users = user_movie_totals[user_movie_totals['movie'] == movie]

        # 1. Rank
        rank_text = f"#{int(movie_ranks[movie])} of {total_movies}"

        # 2. Top Category (Excluding Enjoyable, based on % of max score)
        m_avgs = movie_metric_avgs[movie_metric_avgs['movie'] == movie].copy()
        m_avgs = m_avgs[m_avgs['Metric'] != 'Enjoyable']
        m_avgs['perc'] = m_avgs.apply(lambda x: x['Score'] / m_max_map.get(x['Metric'], 1), axis=1)
        top_metric = m_avgs.loc[m_avgs['perc'].idxmax()]['Metric']

        # 3. Consensus (SD-based)
        sd_val = movie_sd[movie]
        if sd_val < 0.6:
            cont = ("High Agreement", "🤝")
        elif sd_val < 1.5:
            cont = ("Some Debate", "🗣️")
        else:
            cont = ("Highly Controversial", "🔥")

        # 4. The Fan (Highest Total Score)
        fan = m_users.loc[m_users['Score'].idxmax()]

        # 5. The Cynic (Lowest Total Score)
        cynic = m_users.loc[m_users['Score'].idxmin()]

        # 6. The Specialist (Highest % of Category, Tie-break by Lowest Total Score)
        m_ratings = df[(df['movie'] == movie) & (df['Metric'] != 'Enjoyable')].copy()
        m_ratings['perc'] = m_ratings.apply(lambda x: x['Score'] / m_max_map.get(x['Metric'], 1), axis=1)

        # Merge individual ratings with user's total movie score for tie-breaking
        m_ratings = m_ratings.merge(m_users[['user', 'Score']], on='user', suffixes=('', '_total'))

        # Sort: Category % Descending, Total Movie Score Ascending
        spec_df_sorted = m_ratings.sort_values(by=['perc', 'Score_total'], ascending=[False, True])
        spec = spec_df_sorted.iloc[0]

        html_content = f"""{style}<body><div class="grid-container">
            <div class="callout-card"><div class="label">Rank</div><div class="icon">🏆</div><div class="value">{rank_text}</div></div>
            <div class="callout-card"><div class="label">Top Category</div><div class="icon">{icons.get(top_metric, '⭐')}</div><div class="value">{top_metric}</div></div>
            <div class="callout-card"><div class="label">Consensus</div><div class="icon">{cont[1]}</div><div class="value">{cont[0]}</div></div>
            <div class="callout-card"><div class="label">The Fan</div><div class="icon">🤩</div><div class="value">{fan['user']} ({round(fan['Score'], 2):g})</div></div>
            <div class="callout-card"><div class="label">The Cynic</div><div class="icon">😒</div><div class="value">{cynic['user']} ({round(cynic['Score'], 2):g})</div></div>
            <div class="callout-card"><div class="label">The Specialist</div><div class="icon">{icons.get(spec['Metric'], '🎯')}</div><div class="value">{spec['user']} ({spec['Metric']})</div></div>
        </div></body>"""

        with open(os.path.join(movie_path, "callouts.html"), "w", encoding='utf-8') as f:
            f.write(html_content)


def get_radar_chart(dataframe, active_users):
    """
    Generates a radar chart dynamically for all active users.
    dataframe: The main filtered dataframe.
    active_users: A list of user codes (e.g., ['MA', 'YA', 'ZA', 'KS', 'BM', 'KD', 'LD'])
    """
    # 1. Processing Dates (Same as your original logic)
    now = datetime.datetime.now()
    one_year = minus_years(now, 1)
    dataframe = dataframe[dataframe['date'] >= one_year].copy()
    dataframe = dataframe.sort_values(by='date', ascending=False)
    dataframe["date"] = dataframe["date"].astype("datetime64[M]")

    # 2. Setup Categories
    categories_list = dataframe.Metric.unique().tolist()
    # We add the first category to the end to "close" the radar circle
    categories = [*categories_list, categories_list[0]]

    # 3. Merge with Max Ratings for Normalization
    max_ratings_df = pd.read_csv(r'C:\Users\krish\Desktop\DAS\Scores\max_ratings.csv')
    dataframe = dataframe.merge(max_ratings_df, on='Metric', how='left')
    dataframe['score_percent'] = (dataframe['Score'] / dataframe['max_score']) * 100

    # 4. Create Aggregated Mean Data
    # Calculate mean per user per metric
    average_total_scores_df = dataframe.groupby(['user', 'Metric'])['score_percent'].mean().reset_index()
    average_total_scores_df.rename(columns={'score_percent': 'Score'}, inplace=True)
    average_total_scores_df['movie'] = 'Mean'

    # Prepare the dataframe for the dropdown menu (Individual Movies)
    movie_df = dataframe[['user', 'Metric', 'score_percent', 'movie']].copy()
    movie_df.rename(columns={'score_percent': 'Score'}, inplace=True)

    # Combine Mean and Individual Movies
    final_radar_df = pd.concat([average_total_scores_df, movie_df], axis=0)
    movie_list = final_radar_df.movie.unique().tolist()

    # 5. Build the Figure
    fig = go.Figure()

    # We use a helper function logic to build score lists for any given movie/mean
    def get_user_scores_for_view(current_df, user_code):
        user_data = current_df[current_df['user'] == user_code]
        scores = []
        for cat in categories_list:
            val = user_data[user_data['Metric'] == cat]['Score'].values
            scores.append(val[0] if len(val) > 0 else None)
        # Close the loop
        return [*scores, scores[0]]

    # Add initial traces (The "Mean" view)
    mean_view_df = final_radar_df[final_radar_df['movie'] == 'Mean']
    for user in active_users:
        fig.add_trace(go.Scatterpolar(
            r=get_user_scores_for_view(mean_view_df, user),
            theta=categories,
            name=user
        ))

    # 6. Build the Dropdown Menu (Dynamic Buttons)
    buttons = []
    for movie in movie_list:
        current_movie_df = final_radar_df[final_radar_df['movie'] == movie]

        # Calculate score lists for ALL active users for this specific movie
        recalc_r = [get_user_scores_for_view(current_movie_df, user) for user in active_users]

        buttons.append(dict(
            method='update',
            label=movie,
            args=[{'r': recalc_r}]
        ))

    fig.update_layout(
        updatemenus=[dict(
            buttons=buttons,
            direction='down',
            showactive=False,
            pad={"l": 10, "t": 10},
            x=-0.1,
            y=1.2
        )],
        showlegend=True,
        legend=dict(orientation='v', y=0, x=-1),
        paper_bgcolor='#dfe0f7',
        plot_bgcolor='#bec1ef',
        margin=dict(l=0, r=80, t=50, b=40)
    )

    # 7. Save to GitHub Repo folder
    file_path = r"C:\Users\krish\Documents\GIT\dead-auteur-socitey\analysis2\radar.html"
    fig.write_html(file_path, include_plotlyjs='cdn')


def run_script():
    ratings_p = r'C:\Users\krish\Desktop\DAS\Scores\ratings_by_metric.csv'
    config_p = r'C:\Users\krish\Desktop\DAS\Scores\config_users.csv'
    max_p = r'C:\Users\krish\Desktop\DAS\Scores\max_ratings.csv'
    git_p = r"C:\Users\krish\Documents\GIT\dead-auteur-socitey"

    raw_df = pd.read_csv(ratings_p)
    raw_df['date'] = pd.to_datetime(raw_df['date'], format='%d/%m/%Y')

    user_config = pd.read_csv(config_p)
    user_config.columns = user_config.columns.str.strip()
    active_users = user_config[user_config['include'] == 1]['user_code'].tolist()

    max_df = pd.read_csv(max_p)
    max_total = max_df['max_score'].sum()
    metric_max_map = dict(zip(max_df['Metric'].str.capitalize(), max_df['max_score']))

    df_filtered = raw_df[raw_df['user'].isin(active_users)]

    print(f"Generating charts (Total Scale: {max_total})...")
    get_last_year_chart(df_filtered, active_users, git_p, max_total)
    get_top_ten_movie_chart(df_filtered, active_users, git_p, max_total, mode='top')
    get_top_ten_movie_chart(df_filtered, active_users, git_p, max_total, mode='bottom')
    get_average_score_per_voter(df_filtered, active_users, git_p, max_total, metric_max_map)
    get_difference_from_median_raters(df_filtered, git_p)
    get_average_score_per_list_user(df_filtered, user_config, git_p, max_total, metric_max_map)
    get_number_of_movies_attended(df_filtered, git_p)
    get_score_over_time_per_voter(df_filtered, active_users, git_p)
    get_radar_chart(df_filtered, active_users)

    print("Generating movie pages (Horizontal Layout, Poppins/Lato)...")
    generate_movie_pages(df_filtered, git_p, metric_max_map, max_total)

    generate_callout_visuals(df_filtered, max_df, git_p)
    print("Success!")


if __name__ == "__main__":
    run_script()
