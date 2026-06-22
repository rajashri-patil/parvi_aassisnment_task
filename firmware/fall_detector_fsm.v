module fall_detector_fsm (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        sample_valid,
    input  wire [15:0] mag,
    input  wire [15:0] gx,
    input  wire [15:0] gy,
    output reg         alert,
    output reg         ph1_active,
    output reg  [2:0]  state_out
);
    localparam ST_IDLE  = 3'd0;
    localparam ST_FF    = 3'd1;
    localparam ST_IMP   = 3'd2;
    localparam ST_CONF  = 3'd3;
    localparam ST_ALERT = 3'd4;

    localparam FF_LIM   = 16'd50;
    localparam IMP_LIM  = 16'd350;
    localparam GYRO_MIN = 16'd200;
    localparam FF_MIN   = 6'd10;
    localparam IMP_MAX  = 6'd50;

    reg [2:0] state, nxt;
    reg [5:0] ff_cnt;
    reg [5:0] imp_cnt;
    reg       nxt_alert;

    wire gyro_ok = (gx >= GYRO_MIN) || (gy >= GYRO_MIN);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state      <= ST_IDLE;
            ff_cnt     <= 6'd0;
            imp_cnt    <= 6'd0;
            alert      <= 1'b0;
            ph1_active <= 1'b0;
        end else begin
            state <= nxt;
            alert <= nxt_alert;

            if (sample_valid) begin
                case (state)
                    ST_FF:  ff_cnt  <= (mag < FF_LIM) ? ff_cnt + 1 : 6'd0;
                    ST_IMP: imp_cnt <= imp_cnt + 1;
                    default: begin
                        ff_cnt  <= 6'd0;
                        imp_cnt <= 6'd0;
                    end
                endcase
            end

            ph1_active <= (nxt == ST_FF || nxt == ST_IMP) ? 1'b1 : 1'b0;
        end
    end

    always @(*) begin
        nxt       = state;
        nxt_alert = 1'b0;

        if (sample_valid) begin
            case (state)
                ST_IDLE: nxt = (mag < FF_LIM) ? ST_FF : ST_IDLE;

                ST_FF: begin
                    if (mag < FF_LIM)
                        nxt = (ff_cnt >= FF_MIN - 1) ? ST_IMP : ST_FF;
                    else
                        nxt = ST_IDLE;
                end

                ST_IMP: begin
                    if (mag > IMP_LIM)
                        nxt = gyro_ok ? ST_CONF : ST_IDLE;
                    else
                        nxt = (imp_cnt >= IMP_MAX - 1) ? ST_IDLE : ST_IMP;
                end

                ST_CONF: begin
                    nxt_alert = 1'b1;
                    nxt       = ST_ALERT;
                end

                ST_ALERT: nxt = ST_IDLE;

                default: nxt = ST_IDLE;
            endcase
        end
    end

    always @(*) state_out = state;

endmodule


`timescale 1ns/1ps

module fall_detector_fsm_tb;
    reg        clk   = 0;
    reg        rst_n = 0;
    reg        sample_valid;
    reg [15:0] mag;
    reg [15:0] gx;
    reg [15:0] gy;

    wire        alert;
    wire        ph1_active;
    wire [2:0]  state_out;

    fall_detector_fsm dut (
        .clk(clk), .rst_n(rst_n),
        .sample_valid(sample_valid),
        .mag(mag), .gx(gx), .gy(gy),
        .alert(alert),
        .ph1_active(ph1_active),
        .state_out(state_out)
    );

    always #5 clk = ~clk;

    task send;
        input [15:0] m;
        input [15:0] gx_in;
        input [15:0] gy_in;
        begin
            mag = m; gx = gx_in; gy = gy_in;
            sample_valid = 1;
            @(posedge clk);
            sample_valid = 0;
            repeat(100) @(posedge clk);
        end
    endtask

    integer i;
    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, fall_detector_fsm_tb);
        repeat(5) @(posedge clk);
        rst_n = 1;

        for (i = 0; i < 500; i = i+1) send(16'd100, 16'd50, 16'd40);

        for (i = 0; i < 10; i = i+1) send(16'd5, 16'd350, 16'd300);
        send(16'd400, 16'd350, 16'd300);

        for (i = 0; i < 600; i = i+1) send(16'd100, 16'd50, 16'd40);

        for (i = 0; i < 10; i = i+1) send(16'd5, 16'd350, 16'd300);
        send(16'd400, 16'd350, 16'd300);

        for (i = 0; i < 600; i = i+1) send(16'd100, 16'd50, 16'd40);

        for (i = 0; i < 10; i = i+1) send(16'd5, 16'd350, 16'd300);
        send(16'd400, 16'd350, 16'd300);

        send(16'd100, 16'd50, 16'd40);
        $finish;
    end

    always @(posedge clk)
        if (alert) $display("%0t alert", $time);

endmodule