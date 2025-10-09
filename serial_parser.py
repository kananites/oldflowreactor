import pandas as pd
import matplotlib.pyplot as plt
from plot_flow_data import calc_delta_hrs

def plot_MFC(FILEPATH):
    data = []

    with open(FILEPATH) as f:
        for line in f:
            raw_single_line = line.strip().split()
            MFC_index = raw_single_line[0][2]
            line_no_index = raw_single_line[1:]
            processed_line = [MFC_index] + line_no_index
            # added to deal with weird bug where 'MOV\\r\\x00' randomly appears after gas type in some data points
            processed_line = [elem for elem in processed_line if "MOV" not in elem]
            if len(processed_line) != 8:
                print(processed_line)
            data.append(processed_line)

    column_names=['MFC','Abs Pressure','Temperature','Volumetric Flow','Standard Mass Flow','Setpoint', 'Gas Type', 'UTC']
    MFC_df = pd.DataFrame(data, columns=column_names)

    for col in column_names[1:6]:
        MFC_df[col] = pd.to_numeric(MFC_df[col], errors = 'coerce')

    MFC_df['Date'] = pd.to_datetime(MFC_df['UTC'],unit='s')

    calc_delta_hrs(MFC_df,'Date')
    print(MFC_df.dtypes)

    MFC_A_df = MFC_df[MFC_df['MFC'] == 'A']
    MFC_A_gas = MFC_A_df['Gas Type'][0]
    # A_upper = 1.1*MFC_A_df['Standard Mass Flow'].max()
    # A_lower = 0.9*MFC_A_df['Standard Mass Flow'].min()

    MFC_B_df = MFC_df[MFC_df['MFC'] == 'B']
    MFC_B_gas = MFC_B_df['Gas Type'][1]
    # B_upper = 1.1*MFC_B_df['Standard Mass Flow'].max()
    # B_lower = 0.9*MFC_B_df['Standard Mass Flow'].min()

    MFC_C_df = MFC_df[MFC_df['MFC'] == 'C']

    fig, axs = plt.subplots(2,1, sharex = True)
    MFC_A_df.plot(x = 'elapsed_hours', y = 'Standard Mass Flow', color = 'b', ax = axs[0])
    MFC_B_df.plot(x = 'elapsed_hours', y = 'Standard Mass Flow', color = 'b', ax = axs[1])
    axs[0].legend([MFC_A_gas])
    axs[1].legend([MFC_B_gas])
    #axs[0].set_ylim([A_lower,A_upper])
    #axs[1].set_ylim([B_lower,B_upper])
    axs[0].grid(linestyle = '--')
    axs[1].grid(linestyle = '--')
    axs[0].tick_params(direction = 'in', which='both')
    axs[1].tick_params(direction = 'in', which='both')
    axs[0].minorticks_off()
    axs[1].minorticks_off()
    axs[0].set_ylabel('Flow Rate (sccm)')
    axs[1].set_ylabel('Flow Rate (sccm)')
    axs[1].set_xlabel('Elapsed time [hrs]')

    MFC_C_df.plot(x = 'elapsed_hours', y = 'Standard Mass Flow', color = 'b')
    plt.legend(['MFC3'])
    return

if __name__ == '__main__':
    while True:
        try:
            # get pathname for MFC data
            FILEPATH = input('>> Please enter filepath for MFC: ')
            plot_MFC(FILEPATH)
            plt.show()
            break

        except (OSError, SyntaxError):
            print('Error: Check pathname.')
        except (AssertionError, IndexError):
            print('Error: No appropriate .txt files found in folder. Check folder contents.')
        except ValueError:
            print('Error: Unequal number of FID and TCD files. Check folder contents.')

    #sample filepath:
    #FILEPATH = r"C:\Users\Chastity Li\Box Sync\Kanan Lab\Data\Flow Reactor\10-23-20 N5p158\10-23-20 MFC.txt"#log.txt